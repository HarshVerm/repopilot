import asyncio
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.api.routes import github as github_routes
from app.api.routes.github import build_issue_body
from app.core.config import settings
from app.db.models.identity import (
    GitHubInstallation,
    Repository,
    User,
    UserSession,
)
from app.db.session import AsyncSessionLocal
from app.main import app
from app.services.auth.github_tokens import (
    GitHubOAuthTokenSet,
    GitHubUserTokenService,
)
from app.services.auth.service import secret_hash


class FakeGitHub:
    def __init__(self) -> None:
        self.created_issue: dict | None = None

    async def list_repository_tree(
        self,
        installation_id,
        owner,
        repo,
        tree_sha,
    ):
        assert installation_id > 0
        assert (owner, repo, tree_sha) == (
            "example",
            "product",
            "main",
        )
        return {
            "truncated": False,
            "tree": [
                {
                    "type": "blob",
                    "path": "src/api/issues.py",
                },
                {
                    "type": "tree",
                    "path": "src/api",
                },
                {
                    "type": "blob",
                    "path": "README.md",
                },
                {
                    "type": "blob",
                    "path": "../unsafe.txt",
                },
            ],
        }

    async def create_issue_as_user(
        self,
        *,
        access_token,
        owner,
        repo,
        title,
        body,
    ):
        assert access_token == "github-user-token"
        assert (owner, repo) == ("example", "product")
        self.created_issue = {
            "title": title,
            "body": body,
        }
        return {
            "id": 9123,
            "number": 42,
            "title": title,
            "body": body,
            "state": "open",
            "html_url": (
                "https://github.com/example/product/issues/42"
            ),
            "comments": 0,
            "labels": [],
            "user": {"login": "issue-author"},
            "created_at": "2026-07-30T00:00:00Z",
            "updated_at": "2026-07-30T00:00:00Z",
        }


def test_related_file_selection_is_optional():
    assert build_issue_body(
        description="A clear issue description.",
        related_files=[],
    ) == "A clear issue description."


def test_repository_files_and_user_attributed_issue_creation():
    records = asyncio.run(seed_issue_creation_tenant())
    user, installation, repository, token, csrf = records
    fake_github = FakeGitHub()
    app.dependency_overrides[
        github_routes.get_github_app_client
    ] = lambda: fake_github
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

            files_response = client.get(
                (
                    "/api/v1/github/repositories/"
                    f"{repository.id}/files"
                )
            )
            assert files_response.status_code == 200
            assert files_response.json() == {
                "files": [
                    "README.md",
                    "src/api/issues.py",
                ],
                "total": 2,
                "truncated": False,
                "default_branch": "main",
            }

            invalid_response = client.post(
                (
                    "/api/v1/github/repositories/"
                    f"{repository.id}/issues"
                ),
                json={
                    "title": "Invalid file",
                    "description": "This should be rejected.",
                    "related_files": ["missing.py"],
                },
                headers={
                    settings.csrf_header_name: csrf,
                },
            )
            assert invalid_response.status_code == 422
            assert (
                invalid_response.json()["detail"]["error"]["code"]
                == "RELATED_FILES_INVALID"
            )

            create_response = client.post(
                (
                    "/api/v1/github/repositories/"
                    f"{repository.id}/issues"
                ),
                json={
                    "title": "Explain the issue clearly",
                    "description": (
                        "The current behavior is incorrect."
                    ),
                    "related_files": [
                        "src/api/issues.py",
                    ],
                },
                headers={
                    settings.csrf_header_name: csrf,
                },
            )

        assert create_response.status_code == 201, (
            create_response.text
        )
        assert create_response.json()["number"] == 42
        assert fake_github.created_issue == {
            "title": "Explain the issue clearly",
            "body": (
                "The current behavior is incorrect.\n\n"
                "---\n\n"
                "### Related files\n\n"
                "- <code>src/api/issues.py</code>"
            ),
        }
    finally:
        app.dependency_overrides.pop(
            github_routes.get_github_app_client,
            None,
        )
        asyncio.run(
            cleanup_issue_creation_tenant(
                user_id=user.id,
                installation_id=installation.id,
                repository_id=repository.id,
            )
        )


async def seed_issue_creation_tenant():
    suffix = uuid.uuid4().hex
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(24)
    async with AsyncSessionLocal() as db:
        user = User(
            github_user_id=abs(hash(f"issue-{suffix}")),
            github_login=f"issue-author-{suffix}",
        )
        db.add(user)
        await db.flush()
        installation = GitHubInstallation(
            github_installation_id=abs(
                hash(f"installation-{suffix}")
            ),
            user_id=user.id,
            github_account_id=abs(
                hash(f"account-{suffix}")
            ),
            github_account_login=user.github_login,
            account_type="User",
            repository_selection="selected",
            status="active",
        )
        db.add(installation)
        await db.flush()
        repository = Repository(
            installation_id=installation.id,
            github_repository_id=abs(
                hash(f"repository-{suffix}")
            ),
            owner="example",
            name="product",
            full_name="example/product",
            private=True,
            archived=False,
            disabled=False,
            default_branch="main",
            html_url=(
                "https://github.com/example/product"
            ),
            clone_url=(
                "https://github.com/example/product.git"
            ),
            permissions_json={
                "pull": True,
                "push": True,
                "pull_requests": True,
                "issues": True,
            },
            access_status="active",
        )
        db.add(repository)
        db.add(
            UserSession(
                user_id=user.id,
                token_hash=secret_hash(token),
                csrf_token_hash=secret_hash(csrf),
                expires_at=(
                    datetime.now(UTC)
                    + timedelta(hours=1)
                ),
            )
        )
        await db.flush()
        await GitHubUserTokenService().store(
            user_id=user.id,
            token_set=GitHubOAuthTokenSet(
                access_token="github-user-token",
            ),
            db=db,
        )
        return (
            user,
            installation,
            repository,
            token,
            csrf,
        )


async def cleanup_issue_creation_tenant(
    *,
    user_id: uuid.UUID,
    installation_id: uuid.UUID,
    repository_id: uuid.UUID,
) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(
            delete(Repository).where(
                Repository.id == repository_id
            )
        )
        await db.execute(
            delete(GitHubInstallation).where(
                GitHubInstallation.id == installation_id
            )
        )
        await db.execute(
            delete(UserSession).where(
                UserSession.user_id == user_id
            )
        )
        await db.execute(
            delete(User).where(
                User.id == user_id
            )
        )
        await db.commit()
