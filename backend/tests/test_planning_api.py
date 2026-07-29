import asyncio
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.api.routes.indexing import WORKSPACES_DIR
from app.api.routes.plans import (
    get_github_client,
    get_planner_runner,
)
from app.api.routes.retrieval import (
    get_embedding_client,
)
from app.core.config import settings
from app.db.models.execution_plan import ExecutionPlan
from app.db.models.code_index import RepositoryFile
from app.db.session import get_db
from app.main import app
from tests.fakes import FakeEmbeddingClient
from tests.planning_fixtures import (
    FakePlannerRunner,
    valid_planner_output,
)
from tests.retrieval_fixtures import (
    create_retrieval_fixture_repo,
)


test_engine = create_async_engine(
    settings.database_url,
    poolclass=NullPool,
)

TestAsyncSessionLocal = async_sessionmaker(
    bind=test_engine,
    expire_on_commit=False,
)


ISSUE = {
    "id": 1,
    "number": 142,
    "title": "Search doesn't debounce correctly",
    "body": (
        "Search request fires for every keypress.\n"
        "Wait briefly before calling the API."
    ),
    "state": "open",
    "html_url": "https://github.com/acme/storefront/issues/142",
    "comments": 0,
    "labels": [],
}


class FakeGitHubClient:
    async def get_issue(
        self,
        owner: str,
        repo: str,
        issue_number: int,
    ) -> dict:
        assert owner == "acme"
        assert repo == "storefront"
        assert issue_number == 142

        return dict(ISSUE)


async def override_get_db():
    async with TestAsyncSessionLocal() as session:
        yield session


def override_embedding_client():
    return FakeEmbeddingClient()


def override_github_client():
    return FakeGitHubClient()


def override_planner_runner():
    return FakePlannerRunner(
        valid_planner_output()
    )


@pytest.fixture(autouse=True)
def use_test_dependencies():
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[
        get_embedding_client
    ] = override_embedding_client
    app.dependency_overrides[
        get_github_client
    ] = override_github_client
    app.dependency_overrides[
        get_planner_runner
    ] = override_planner_runner

    yield

    app.dependency_overrides.pop(
        get_db,
        None,
    )
    app.dependency_overrides.pop(
        get_embedding_client,
        None,
    )
    app.dependency_overrides.pop(
        get_github_client,
        None,
    )
    app.dependency_overrides.pop(
        get_planner_runner,
        None,
    )


async def delete_workspace(
    workspace_id: str,
) -> None:
    async with TestAsyncSessionLocal() as db:
        await db.execute(
            delete(ExecutionPlan).where(
                ExecutionPlan.workspace_id
                == workspace_id
            )
        )
        await db.execute(
            delete(RepositoryFile).where(
                RepositoryFile.workspace_id
                == workspace_id
            )
        )
        await db.commit()


async def dispose_database_engine() -> None:
    await test_engine.dispose()


def git_status(
    repo: Path,
) -> str:
    result = subprocess.run(
        [
            "git",
            "status",
            "--porcelain",
        ],
        cwd=repo,
        capture_output=True,
        check=True,
        text=True,
    )

    return result.stdout


def test_plan_api_end_to_end_and_state_transitions_without_source_changes():
    workspace_id = str(uuid.uuid4())
    workspace_path = (
        WORKSPACES_DIR / workspace_id
    )
    repo = workspace_path / "repository"
    create_retrieval_fixture_repo(repo)
    before_status = git_status(repo)

    try:
        with TestClient(app) as test_client:
            index_response = test_client.post(
                f"/api/v1/index/{workspace_id}"
            )
            build_response = test_client.post(
                f"/api/v1/retrieval/{workspace_id}/build"
            )
            plan_response = test_client.post(
                f"/api/v1/workspaces/{workspace_id}/plan",
                json={
                    "owner": "acme",
                    "repo": "storefront",
                    "issue_number": 142,
                },
            )

            assert index_response.status_code == 200
            assert build_response.status_code == 200
            assert plan_response.status_code == 200

            body = plan_response.json()
            plan_id = body["plan_id"]
            assert body["status"] == "pending_approval"
            assert body["plan"]["summary"] == (
                "Search execution is tied to immediate input updates."
            )
            assert body["plan"]["files_to_modify"][0]["path"] == (
                "src/components/SearchBox.tsx"
            )

            get_response = test_client.get(
                f"/api/v1/plans/{plan_id}"
            )
            approve_response = test_client.post(
                f"/api/v1/plans/{plan_id}/approve"
            )
            approve_again_response = test_client.post(
                f"/api/v1/plans/{plan_id}/approve"
            )
            missing_response = test_client.post(
                f"/api/v1/plans/{uuid.uuid4()}/approve"
            )

            second_plan = test_client.post(
                f"/api/v1/workspaces/{workspace_id}/plan",
                json={
                    "owner": "acme",
                    "repo": "storefront",
                    "issue_number": 142,
                },
            )
            rejected_plan_id = second_plan.json()[
                "plan_id"
            ]
            reject_response = test_client.post(
                f"/api/v1/plans/{rejected_plan_id}/reject",
                json={
                    "reason": "Need a smaller scope"
                },
            )
            reject_again_response = test_client.post(
                f"/api/v1/plans/{rejected_plan_id}/reject",
                json={
                    "reason": "Already rejected"
                },
            )

        assert get_response.status_code == 200
        assert approve_response.status_code == 200
        assert approve_response.json()["status"] == "approved"
        assert approve_again_response.status_code == 409
        assert missing_response.status_code == 404
        assert second_plan.status_code == 200
        assert reject_response.status_code == 200
        assert reject_response.json()["status"] == "rejected"
        assert reject_response.json()["rejection_reason"] == "Need a smaller scope"
        assert reject_again_response.status_code == 409
        assert git_status(repo) == before_status
    finally:
        asyncio.run(dispose_database_engine())
        asyncio.run(
            delete_workspace(
                workspace_id
            )
        )
        asyncio.run(dispose_database_engine())
        shutil.rmtree(
            workspace_path,
            ignore_errors=True,
        )


def test_plan_api_validation_errors():
    workspace_id = str(uuid.uuid4())

    with TestClient(app) as test_client:
        invalid_workspace = test_client.post(
            "/api/v1/workspaces/not-a-uuid/plan",
            json={
                "owner": "acme",
                "repo": "storefront",
                "issue_number": 142,
            },
        )
        invalid_issue = test_client.post(
            f"/api/v1/workspaces/{workspace_id}/plan",
            json={
                "owner": "acme",
                "repo": "storefront",
                "issue_number": 0,
            },
        )
        missing_workspace = test_client.post(
            f"/api/v1/workspaces/{workspace_id}/plan",
            json={
                "owner": "acme",
                "repo": "storefront",
                "issue_number": 142,
            },
        )

    assert invalid_workspace.status_code == 422
    assert invalid_issue.status_code == 422
    assert missing_workspace.status_code == 404
