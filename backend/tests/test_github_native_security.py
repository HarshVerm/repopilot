import asyncio
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.config import settings
from app.db.models.identity import (
    GitHubInstallation,
    OAuthState,
    Repository,
    User,
    UserSession,
)
from app.db.models.task import RepoPilotTask
from app.db.models.task_event import TaskEvent
from app.db.session import AsyncSessionLocal, engine
from app.main import app
from app.api.routes import github as github_routes
from app.api.routes import tasks as task_routes
from app.api.routes.tasks import get_github_app_client
from app.services.auth.authorization import authorize_task
from app.services.auth.service import (
    AuthService,
    get_optional_auth_context,
    secret_hash,
)
from app.services.github.app_client import (
    GitHubAppClient,
    GitHubAppConfigurationError,
    missing_github_app_settings,
)
from app.services.reviews.service import (
    ReviewService,
    ReviewStateError,
)
from app.services.tasks.service import TaskService


def test_native_task_create_returns_committed_task(
    monkeypatch,
):
    async def seed():
        user, other_user = await seed_users()
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(24)
        async with AsyncSessionLocal() as db:
            installation = installation_for(user)
            db.add(installation)
            await db.flush()
            repository = repository_for(
                installation,
                "native/create",
            )
            db.add(repository)
            db.add(
                UserSession(
                    user_id=user.id,
                    token_hash=secret_hash(token),
                    csrf_token_hash=secret_hash(csrf),
                    expires_at=datetime.now(UTC)
                    + timedelta(hours=1),
                )
            )
            await db.commit()
        return (
            user,
            other_user,
            installation,
            repository,
            token,
            csrf,
        )

    class FakeGitHubApp:
        async def get_issue(
            self,
            _installation_id,
            _owner,
            _repo,
            issue_number,
        ):
            return issue_payload(issue_number)

    async def no_op_background(_task_id):
        return None

    records = asyncio.run(seed())
    (
        user,
        other_user,
        installation,
        repository,
        token,
        csrf,
    ) = records
    task_ids = []
    app.dependency_overrides[
        get_github_app_client
    ] = lambda: FakeGitHubApp()
    monkeypatch.setattr(
        task_routes,
        "run_task_background",
        no_op_background,
    )
    try:
        with TestClient(app) as client:
            client.cookies.set(
                settings.session_cookie_name,
                token,
            )
            client.cookies.set(
                settings.csrf_cookie_name,
                csrf,
            )
            response = client.post(
                "/api/v1/tasks",
                json={
                    "repository_id": str(repository.id),
                    "issue_number": 1,
                },
                headers={
                    settings.csrf_header_name: csrf,
                },
            )
        if response.status_code == 200:
            task_ids.append(
                uuid.UUID(response.json()["task_id"])
            )
        else:
            async def find_created_tasks():
                async with AsyncSessionLocal() as db:
                    return list(
                        await db.scalars(
                            select(RepoPilotTask.id).where(
                                RepoPilotTask.repository_id
                                == repository.id
                            )
                        )
                    )

            task_ids.extend(
                asyncio.run(find_created_tasks())
            )
        assert response.status_code == 200, response.text
    finally:
        app.dependency_overrides.pop(
            get_github_app_client,
            None,
        )
        asyncio.run(
            cleanup_tenant_records(
                user_ids=[user.id, other_user.id],
                task_ids=task_ids,
                repository_ids=[repository.id],
                installation_ids=[installation.id],
            )
        )


@pytest.mark.parametrize(
    "initial_status",
    [
        "failed",
        "plan_revision_required",
    ],
)
def test_stopped_native_task_restart_creates_deduplicated_attempt(
    monkeypatch,
    initial_status,
):
    async def seed():
        user, other_user = await seed_users()
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(24)
        async with AsyncSessionLocal() as db:
            installation = installation_for(user)
            db.add(installation)
            await db.flush()
            repository = repository_for(
                installation,
                "native/restart",
            )
            db.add(repository)
            await db.flush()
            failed_task = await TaskService().create_task(
                owner=repository.owner,
                repo=repository.name,
                issue_number=7,
                db=db,
                user_id=user.id,
                installation_id=installation.id,
                repository_id=repository.id,
                issue_snapshot=issue_payload(7),
                issue_summary="Original summary",
                user_instructions="Preserve this instruction.",
                base_branch=repository.default_branch,
                autonomy_mode="standard",
            )
            if initial_status == "failed":
                failed_task = await TaskService().set_failure(
                    task_id=failed_task.id,
                    db=db,
                    failure_category="sandbox_error",
                    error=RuntimeError(
                        "Original execution failed"
                    ),
                )
            else:
                failed_task.status = (
                    "plan_revision_required"
                )
                failed_task.current_step = 5
                failed_task.failure_category = (
                    "plan_revision_required"
                )
                failed_task.last_error = (
                    "Planner needs more context"
                )
                await db.commit()
                await db.refresh(
                    failed_task
                )
            db.add(
                UserSession(
                    user_id=user.id,
                    token_hash=secret_hash(token),
                    csrf_token_hash=secret_hash(csrf),
                    expires_at=datetime.now(UTC)
                    + timedelta(hours=1),
                )
            )
            await db.commit()
        return (
            user,
            other_user,
            installation,
            repository,
            failed_task,
            token,
            csrf,
        )

    class FakeGitHubApp:
        async def get_issue(
            self,
            installation_id,
            owner,
            repo,
            issue_number,
        ):
            assert installation_id == installation.github_installation_id
            assert (owner, repo, issue_number) == (
                "native",
                "restart",
                7,
            )
            return {
                **issue_payload(7),
                "body": "Latest issue body",
            }

    async def no_op_background(_task_id):
        return None

    records = asyncio.run(seed())
    (
        user,
        other_user,
        installation,
        repository,
        failed_task,
        token,
        csrf,
    ) = records
    created_task_ids = [failed_task.id]
    app.dependency_overrides[
        get_github_app_client
    ] = lambda: FakeGitHubApp()
    monkeypatch.setattr(
        task_routes,
        "run_task_background",
        no_op_background,
    )
    try:
        with TestClient(app) as client:
            client.cookies.set(
                settings.session_cookie_name,
                token,
            )
            client.cookies.set(
                settings.csrf_cookie_name,
                csrf,
            )
            missing_csrf = client.post(
                f"/api/v1/tasks/{failed_task.id}/restart"
            )
            assert missing_csrf.status_code == 403
            first = client.post(
                f"/api/v1/tasks/{failed_task.id}/restart",
                headers={
                    settings.csrf_header_name: csrf,
                },
            )
            assert first.status_code == 200, first.text
            restarted_id = uuid.UUID(
                first.json()["task_id"]
            )
            created_task_ids.append(restarted_id)
            second = client.post(
                f"/api/v1/tasks/{failed_task.id}/restart",
                headers={
                    settings.csrf_header_name: csrf,
                },
            )
            active_conflict = client.post(
                f"/api/v1/tasks/{restarted_id}/restart",
                headers={
                    settings.csrf_header_name: csrf,
                },
            )

        assert restarted_id != failed_task.id
        assert first.json()["status"] == "created"
        assert (
            first.json()["issue"]["body"]
            == "Latest issue body"
        )
        assert (
            first.json()["user_instructions"]
            == "Preserve this instruction."
        )
        assert second.status_code == 200
        assert second.json()["task_id"] == str(
            restarted_id
        )
        assert active_conflict.status_code == 409

        async def assert_audit_events():
            async with AsyncSessionLocal() as db:
                events = list(
                    await db.scalars(
                        select(TaskEvent).where(
                            TaskEvent.task_id.in_(
                                [
                                    failed_task.id,
                                    restarted_id,
                                ]
                            ),
                            TaskEvent.event_type.in_(
                                [
                                    "task.restart_requested",
                                    "task.restarted",
                                ]
                            ),
                        )
                    )
                )
                assert {
                    event.event_type
                    for event in events
                } == {
                    "task.restart_requested",
                    "task.restarted",
                }

        asyncio.run(
            assert_audit_events()
        )
    finally:
        app.dependency_overrides.pop(
            get_github_app_client,
            None,
        )
        asyncio.run(
            cleanup_tenant_records(
                user_ids=[
                    user.id,
                    other_user.id,
                ],
                task_ids=created_task_ids,
                repository_ids=[
                    repository.id,
                ],
                installation_ids=[
                    installation.id,
                ],
            )
        )


def test_repository_list_refreshes_newly_granted_repositories():
    async def seed():
        user, other_user = await seed_users()
        token = secrets.token_urlsafe(32)
        async with AsyncSessionLocal() as db:
            installation = installation_for(user)
            db.add(installation)
            db.add(
                UserSession(
                    user_id=user.id,
                    token_hash=secret_hash(token),
                    csrf_token_hash=secret_hash("csrf"),
                    expires_at=datetime.now(UTC)
                    + timedelta(hours=1),
                )
            )
            await db.commit()
        return user, other_user, installation, token

    class FakeGitHubApp:
        def __init__(self):
            self.calls = []

        async def get_installation(
            self,
            github_installation_id,
        ):
            assert (
                github_installation_id
                == installation.github_installation_id
            )
            return {
                "permissions": {
                    "contents": "write",
                    "pull_requests": "write",
                }
            }

        async def list_installation_repositories(
            self,
            github_installation_id,
            *,
            per_page,
            page,
        ):
            self.calls.append(
                (github_installation_id, per_page, page)
            )
            return {
                "total_count": 1,
                "repositories": [
                    {
                        "id": abs(hash(uuid.uuid4().hex)),
                        "name": "newly-granted",
                        "full_name": "native/newly-granted",
                        "private": True,
                        "archived": False,
                        "disabled": False,
                        "default_branch": "main",
                        "html_url": (
                            "https://github.com/native/newly-granted"
                        ),
                        "clone_url": (
                            "https://github.com/native/"
                            "newly-granted.git"
                        ),
                        "permissions": {
                            "pull": True,
                            "push": True,
                        },
                        "owner": {
                            "login": "native",
                        },
                    }
                ],
            }

    user, other_user, installation, token = asyncio.run(seed())
    github = FakeGitHubApp()
    app.dependency_overrides[
        github_routes.get_github_app_client
    ] = lambda: github
    try:
        with TestClient(app) as client:
            client.cookies.set(
                settings.session_cookie_name,
                token,
            )
            cached = client.get(
                "/api/v1/github/repositories"
            )
            refreshed = client.get(
                "/api/v1/github/repositories",
                params={
                    "refresh": "true",
                },
            )

        assert cached.status_code == 200
        assert cached.json()["repositories"] == []
        assert refreshed.status_code == 200
        assert [
            repository["full_name"]
            for repository in refreshed.json()["repositories"]
        ] == ["native/newly-granted"]
        assert refreshed.json()["repositories"][0][
            "permissions"
        ] == {
            "pull": True,
            "push": True,
            "pull_requests": True,
        }
        assert github.calls == [
            (
                installation.github_installation_id,
                100,
                1,
            )
        ]
    finally:
        app.dependency_overrides.pop(
            github_routes.get_github_app_client,
            None,
        )
        asyncio.run(
            cleanup_tenant_records(
                user_ids=[user.id, other_user.id],
                task_ids=[],
                repository_ids=[],
                installation_ids=[installation.id],
            )
        )


def test_missing_github_private_key_is_actionable(
    monkeypatch,
):
    monkeypatch.setattr(settings, "github_app_id", "123456")
    monkeypatch.setattr(
        settings,
        "github_app_client_id",
        "Iv1.client",
    )
    monkeypatch.setattr(
        settings,
        "github_app_client_secret",
        "secret",
    )
    monkeypatch.setattr(
        settings,
        "github_app_private_key",
        None,
    )
    monkeypatch.setattr(
        settings,
        "github_app_private_key_path",
        None,
    )
    monkeypatch.setattr(
        settings,
        "github_app_slug",
        "repopilot",
    )

    assert missing_github_app_settings() == [
        "GITHUB_APP_PRIVATE_KEY"
    ]
    try:
        GitHubAppClient().app_jwt()
    except GitHubAppConfigurationError as exc:
        assert "GITHUB_APP_PRIVATE_KEY" in str(exc)
    else:
        raise AssertionError(
            "Missing GitHub App private key was accepted"
        )


def test_login_without_github_config_redirects_to_actionable_error(
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "github_app_client_id",
        None,
    )
    monkeypatch.setattr(
        settings,
        "github_app_client_secret",
        None,
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/auth/github/login",
            follow_redirects=False,
        )

    assert response.status_code == 307
    assert response.headers["location"] == (
        f"{settings.frontend_url.rstrip('/')}"
        "/login?error=github-auth-not-configured"
    )


def test_oauth_state_is_single_use_and_bound_to_user():
    async def run():
        user_a, user_b = await seed_users()
        try:
            async with AsyncSessionLocal() as db:
                state = await AuthService().create_oauth_state(
                    db=db,
                    purpose="installation",
                    user_id=user_a.id,
                )
                try:
                    await AuthService().consume_oauth_state(
                        state=state,
                        purpose="installation",
                        user_id=user_b.id,
                        db=db,
                    )
                except HTTPException as exc:
                    assert exc.status_code == 400
                else:
                    raise AssertionError(
                        "Cross-user OAuth state was accepted"
                    )

                record = await AuthService().consume_oauth_state(
                    state=state,
                    purpose="installation",
                    user_id=user_a.id,
                    db=db,
                )
                assert record.used_at is not None

                try:
                    await AuthService().consume_oauth_state(
                        state=state,
                        purpose="installation",
                        user_id=user_a.id,
                        db=db,
                    )
                except HTTPException as exc:
                    assert exc.status_code == 400
                else:
                    raise AssertionError(
                        "OAuth state replay was accepted"
                    )
        finally:
            await cleanup_users([user_a.id, user_b.id])

    asyncio.run(run())


def test_login_callback_establishes_session_and_logout_revokes_it(
    monkeypatch,
):
    github_user_id = abs(hash(uuid.uuid4().hex))

    async def create_state():
        async with AsyncSessionLocal() as db:
            return await AuthService().create_oauth_state(
                db=db,
                purpose="login",
                redirect_path="/tasks",
            )

    async def exchange_code(_service, code):
        assert code == "one-time-code"
        return "ephemeral-user-token"

    async def fetch_identity(_service, access_token):
        assert access_token == "ephemeral-user-token"
        return (
            {
                "id": github_user_id,
                "login": "oauth-user",
                "name": "OAuth User",
                "avatar_url": "https://avatars.example/user",
            },
            "oauth@example.com",
            [],
        )

    monkeypatch.setattr(
        AuthService,
        "exchange_code",
        exchange_code,
    )
    monkeypatch.setattr(
        AuthService,
        "fetch_github_identity",
        fetch_identity,
    )
    user_id = None
    try:
        with TestClient(app) as client:
            callback = client.get(
                "/api/v1/auth/github/callback",
                params={
                    "code": "one-time-code",
                    "state": asyncio.run(create_state()),
                },
                follow_redirects=False,
            )
            assert callback.status_code == 307
            assert callback.headers["location"].endswith(
                "/tasks"
            )
            assert "HttpOnly" in callback.headers["set-cookie"]

            me = client.get("/api/v1/auth/me")
            assert me.status_code == 200
            assert me.json()["github_user_id"] == github_user_id
            user_id = uuid.UUID(me.json()["user_id"])

            csrf = client.cookies.get(
                settings.csrf_cookie_name
            )
            logout = client.post(
                "/api/v1/auth/logout",
                headers={
                    settings.csrf_header_name: csrf,
                },
            )
            assert logout.status_code == 200
            assert logout.json() == {"logged_out": True}
            assert client.get(
                "/api/v1/auth/me"
            ).status_code == 401
    finally:
        if user_id is not None:
            asyncio.run(cleanup_users([user_id]))


def test_expired_session_is_rejected():
    async def run():
        user, other_user = await seed_users()
        raw_token = secrets.token_urlsafe(32)
        try:
            async with AsyncSessionLocal() as db:
                db.add(
                    UserSession(
                        user_id=user.id,
                        token_hash=secret_hash(raw_token),
                        csrf_token_hash=secret_hash("csrf"),
                        expires_at=datetime.now(UTC)
                        - timedelta(seconds=1),
                    )
                )
                await db.commit()
                request = request_with_cookie(raw_token)
                try:
                    await get_optional_auth_context(
                        request=request,
                        db=db,
                    )
                except HTTPException as exc:
                    assert exc.status_code == 401
                    assert (
                        exc.headers["X-Error-Code"]
                        == "SESSION_EXPIRED"
                    )
                else:
                    raise AssertionError(
                        "Expired session was accepted"
                    )
        finally:
            await cleanup_users(
                [user.id, other_user.id]
            )

    asyncio.run(run())


def test_installation_verification_rejects_unowned_installation(
    monkeypatch,
):
    async def seed():
        user, other_user = await seed_users()
        raw_token = secrets.token_urlsafe(32)
        async with AsyncSessionLocal() as db:
            state = await AuthService().create_oauth_state(
                db=db,
                purpose="installation_verification",
                user_id=user.id,
                github_installation_id=987654321,
                redirect_path="/settings",
            )
            db.add(
                UserSession(
                    user_id=user.id,
                    token_hash=secret_hash(raw_token),
                    csrf_token_hash=secret_hash("csrf"),
                    expires_at=datetime.now(UTC)
                    + timedelta(hours=1),
                )
            )
            await db.commit()
        return user, other_user, raw_token, state

    user, other_user, raw_token, state = asyncio.run(seed())

    async def exchange_code(_service, code):
        assert code == "temporary-code"
        return "ephemeral-user-token"

    async def fetch_identity(_service, access_token):
        assert access_token == "ephemeral-user-token"
        return (
            {
                "id": user.github_user_id,
                "login": user.github_login,
            },
            None,
            [],
        )

    monkeypatch.setattr(
        AuthService,
        "exchange_code",
        exchange_code,
    )
    monkeypatch.setattr(
        AuthService,
        "fetch_github_identity",
        fetch_identity,
    )
    try:
        with TestClient(app) as client:
            client.cookies.set(
                settings.session_cookie_name,
                raw_token,
            )
            response = client.get(
                "/api/v1/auth/github/callback",
                params={
                    "code": "temporary-code",
                    "state": state,
                },
                follow_redirects=False,
            )
        assert response.status_code == 403
        assert (
            response.headers["X-Error-Code"]
            == "GITHUB_INSTALLATION_NOT_AUTHORIZED"
        )
    finally:
        asyncio.run(
            cleanup_users([user.id, other_user.id])
        )


def test_tenant_task_and_repository_isolation_through_api():
    async def seed():
        user_a, user_b = await seed_users()
        async with AsyncSessionLocal() as db:
            installation_a = installation_for(user_a)
            installation_b = installation_for(user_b)
            db.add_all([installation_a, installation_b])
            await db.flush()
            repository_a = repository_for(
                installation_a,
                "alpha/project",
            )
            repository_b = repository_for(
                installation_b,
                "beta/secret",
            )
            db.add_all([repository_a, repository_b])
            await db.flush()
            task_a = await TaskService().create_task(
                owner="alpha",
                repo="project",
                issue_number=1,
                db=db,
                user_id=user_a.id,
                installation_id=installation_a.id,
                repository_id=repository_a.id,
                issue_snapshot=issue_payload(1),
                autonomy_mode="standard",
            )
            task_b = await TaskService().create_task(
                owner="beta",
                repo="secret",
                issue_number=2,
                db=db,
                user_id=user_b.id,
                installation_id=installation_b.id,
                repository_id=repository_b.id,
                issue_snapshot=issue_payload(2),
                autonomy_mode="standard",
            )
            token = secrets.token_urlsafe(32)
            csrf = secrets.token_urlsafe(24)
            db.add(
                UserSession(
                    user_id=user_a.id,
                    token_hash=secret_hash(token),
                    csrf_token_hash=secret_hash(csrf),
                    expires_at=datetime.now(UTC)
                    + timedelta(hours=1),
                )
            )
            await db.commit()
            return (
                user_a,
                user_b,
                installation_a,
                installation_b,
                repository_a,
                repository_b,
                task_a,
                task_b,
                token,
                csrf,
            )

    records = asyncio.run(seed())
    (
        user_a,
        user_b,
        installation_a,
        installation_b,
        repository_a,
        repository_b,
        task_a,
        task_b,
        token,
        csrf,
    ) = records
    try:
        with TestClient(app) as client:
            client.cookies.set(
                settings.session_cookie_name,
                token,
            )
            client.cookies.set(
                settings.csrf_cookie_name,
                csrf,
            )
            own = client.get(
                f"/api/v1/tasks/{task_a.id}"
            )
            other = client.get(
                f"/api/v1/tasks/{task_b.id}"
            )
            other_timeline = client.get(
                f"/api/v1/tasks/{task_b.id}/timeline"
            )
            other_metrics = client.get(
                f"/api/v1/tasks/{task_b.id}/metrics"
            )
            other_cancel = client.post(
                f"/api/v1/tasks/{task_b.id}/cancel",
                headers={
                    settings.csrf_header_name: csrf
                },
            )
            other_restart = client.post(
                f"/api/v1/tasks/{task_b.id}/restart",
                headers={
                    settings.csrf_header_name: csrf
                },
            )
            tasks = client.get("/api/v1/tasks")
            repositories = client.get(
                "/api/v1/github/repositories"
            )
            other_repository = client.get(
                f"/api/v1/github/repositories/{repository_b.id}"
            )

        assert own.status_code == 200
        assert other.status_code == 404
        assert other_timeline.status_code == 404
        assert other_metrics.status_code == 404
        assert other_cancel.status_code == 404
        assert other_restart.status_code == 404
        assert [
            item["task_id"]
            for item in tasks.json()["tasks"]
        ] == [str(task_a.id)]
        assert [
            item["id"]
            for item in repositories.json()["repositories"]
        ] == [str(repository_a.id)]
        assert other_repository.status_code == 404
    finally:
        asyncio.run(
            cleanup_tenant_records(
                user_ids=[user_a.id, user_b.id],
                task_ids=[task_a.id, task_b.id],
                repository_ids=[
                    repository_a.id,
                    repository_b.id,
                ],
                installation_ids=[
                    installation_a.id,
                    installation_b.id,
                ],
            )
        )


def test_issue_snapshot_and_user_instructions_are_persisted():
    async def run():
        user, other_user = await seed_users()
        task = None
        try:
            async with AsyncSessionLocal() as db:
                task = await TaskService().create_task(
                    owner="snapshot",
                    repo="repo",
                    issue_number=42,
                    db=db,
                    user_id=user.id,
                    issue_snapshot=issue_payload(42),
                    issue_summary="Problem\nSnapshot test",
                    user_instructions="Do not add dependencies.",
                    autonomy_mode="standard",
                )
                assert task.github_issue_id == 1042
                assert task.issue_title == "Issue 42"
                assert task.issue_body_snapshot == "Original body"
                assert task.issue_labels == ["bug"]
                assert task.issue_summary == "Problem\nSnapshot test"
                assert (
                    task.user_instructions
                    == "Do not add dependencies."
                )
                assert task.autonomy_mode == "standard"
        finally:
            await cleanup_tenant_records(
                user_ids=[user.id],
                task_ids=[task.id] if task else [],
                repository_ids=[],
                installation_ids=[],
            )
            await cleanup_users([other_user.id])

    asyncio.run(run())


def test_issue_selector_filters_pull_requests(monkeypatch):
    issue = {
        **issue_payload(7),
        "state": "open",
        "comments": 2,
    }
    pull_request = {
        **issue_payload(8),
        "state": "open",
        "comments": 0,
        "pull_request": {
            "url": "https://api.github.com/pulls/8"
        },
    }

    class FakeGitHub:
        async def list_issues(
            self,
            owner: str,
            repo: str,
            state: str,
        ):
            assert (owner, repo, state) == (
                "private-owner",
                "private-repo",
                "open",
            )
            return [issue, pull_request]

    monkeypatch.setattr(
        github_routes,
        "github_client",
        FakeGitHub(),
    )
    result = asyncio.run(
        github_routes.list_repository_issues(
            owner="private-owner",
            repo="private-repo",
            state="open",
        )
    )
    assert [item.number for item in result] == [7]


def test_authorization_hides_cross_user_task_and_review_staleness():
    async def run():
        user_a, user_b = await seed_users()
        task = None
        try:
            async with AsyncSessionLocal() as db:
                task = await TaskService().create_task(
                    owner="hidden",
                    repo="task",
                    issue_number=9,
                    db=db,
                    user_id=user_b.id,
                )
                session = UserSession(
                    user_id=user_a.id,
                    token_hash=secret_hash(
                        secrets.token_urlsafe(32)
                    ),
                    csrf_token_hash=secret_hash("csrf"),
                    expires_at=datetime.now(UTC)
                    + timedelta(hours=1),
                )
                db.add(session)
                await db.commit()
                from app.services.auth.service import AuthContext

                try:
                    await authorize_task(
                        task_id=task.id,
                        auth=AuthContext(
                            user=user_a,
                            session=session,
                        ),
                        db=db,
                    )
                except HTTPException as exc:
                    assert exc.status_code == 404
                else:
                    raise AssertionError(
                        "Cross-user task authorization succeeded"
                    )

                fake_review = type(
                    "Review",
                    (),
                    {
                        "change_set_id": uuid.uuid4(),
                        "diff_hash": "a" * 64,
                    },
                )()
                try:
                    ReviewService().validate_expected_review(
                        review=fake_review,
                        expected_change_set_id=uuid.uuid4(),
                        expected_diff_hash="b" * 64,
                    )
                except ReviewStateError:
                    pass
                else:
                    raise AssertionError(
                        "Stale review integrity was accepted"
                    )
        finally:
            await cleanup_tenant_records(
                user_ids=[user_a.id, user_b.id],
                task_ids=[task.id] if task else [],
                repository_ids=[],
                installation_ids=[],
            )

    asyncio.run(run())


async def seed_users() -> tuple[User, User]:
    suffix = uuid.uuid4().hex
    async with AsyncSessionLocal() as db:
        user_a = User(
            github_user_id=abs(hash(f"a-{suffix}")),
            github_login=f"alpha-{suffix}",
        )
        user_b = User(
            github_user_id=abs(hash(f"b-{suffix}")),
            github_login=f"beta-{suffix}",
        )
        db.add_all([user_a, user_b])
        await db.commit()
        await db.refresh(user_a)
        await db.refresh(user_b)
        return user_a, user_b


def installation_for(user: User) -> GitHubInstallation:
    external = abs(hash(uuid.uuid4().hex))
    return GitHubInstallation(
        github_installation_id=external,
        user_id=user.id,
        github_account_id=external,
        github_account_login=user.github_login,
        account_type="User",
        repository_selection="selected",
        status="active",
    )


def repository_for(
    installation: GitHubInstallation,
    full_name: str,
) -> Repository:
    owner, name = full_name.split("/")
    return Repository(
        installation_id=installation.id,
        github_repository_id=abs(
            hash(uuid.uuid4().hex)
        ),
        owner=owner,
        name=name,
        full_name=full_name,
        private=True,
        archived=False,
        disabled=False,
        default_branch="main",
        html_url=f"https://github.com/{full_name}",
        clone_url=f"https://github.com/{full_name}.git",
        permissions_json={
            "pull": True,
            "push": True,
        },
        access_status="active",
    )


def issue_payload(number: int) -> dict:
    return {
        "id": 1000 + number,
        "number": number,
        "title": f"Issue {number}",
        "body": "Original body",
        "html_url": (
            f"https://github.com/example/repo/issues/{number}"
        ),
        "labels": [{"name": "bug"}],
        "user": {"login": "octocat"},
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-02T00:00:00Z",
    }


def request_with_cookie(token: str):
    from starlette.requests import Request

    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [
                (
                    b"cookie",
                    (
                        f"{settings.session_cookie_name}={token}"
                    ).encode(),
                )
            ],
        }
    )


async def cleanup_users(user_ids: list[uuid.UUID]) -> None:
    await cleanup_tenant_records(
        user_ids=user_ids,
        task_ids=[],
        repository_ids=[],
        installation_ids=[],
    )


async def cleanup_tenant_records(
    *,
    user_ids: list[uuid.UUID],
    task_ids: list[uuid.UUID],
    repository_ids: list[uuid.UUID],
    installation_ids: list[uuid.UUID],
) -> None:
    async with AsyncSessionLocal() as db:
        if installation_ids:
            installation_repository_ids = await db.scalars(
                select(Repository.id).where(
                    Repository.installation_id.in_(
                        installation_ids
                    )
                )
            )
            repository_ids = list(
                {
                    *repository_ids,
                    *installation_repository_ids,
                }
            )
        if repository_ids:
            repository_task_ids = await db.scalars(
                select(RepoPilotTask.id).where(
                    RepoPilotTask.repository_id.in_(
                        repository_ids
                    )
                )
            )
            task_ids = list(
                {
                    *task_ids,
                    *repository_task_ids,
                }
            )
        if task_ids:
            await db.execute(
                delete(TaskEvent).where(
                    TaskEvent.task_id.in_(task_ids)
                )
            )
            await db.execute(
                delete(RepoPilotTask).where(
                    RepoPilotTask.id.in_(task_ids)
                )
            )
        if repository_ids:
            await db.execute(
                delete(Repository).where(
                    Repository.id.in_(repository_ids)
                )
            )
        if installation_ids:
            await db.execute(
                delete(GitHubInstallation).where(
                    GitHubInstallation.id.in_(
                        installation_ids
                    )
                )
            )
        await db.execute(
            delete(UserSession).where(
                UserSession.user_id.in_(user_ids)
            )
        )
        await db.execute(
            delete(OAuthState).where(
                OAuthState.user_id.in_(user_ids)
            )
        )
        await db.execute(
            delete(User).where(User.id.in_(user_ids))
        )
        await db.commit()


def teardown_module():
    asyncio.run(engine.dispose())
