import asyncio
import shutil
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.api.routes.coding import (
    get_coder_runner,
)
from app.api.routes.indexing import WORKSPACES_DIR
from app.api.routes.plans import (
    get_github_client,
)
from app.api.routes.retrieval import (
    get_embedding_client,
)
from app.core.config import settings
from app.db.models.change_set import (
    ChangeSet,
)
from app.db.models.execution_plan import (
    ExecutionPlan,
)
from app.db.session import get_db
from app.main import app
from tests.coding_fixtures import (
    FakeCoderRunner,
    create_coding_fixture_repo,
    successful_searchbox_scenario,
)
from tests.fakes import FakeEmbeddingClient
from tests.planning_fixtures import (
    valid_planner_output,
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
        return dict(ISSUE)


async def override_get_db():
    async with TestAsyncSessionLocal() as session:
        yield session


def override_embedding_client():
    return FakeEmbeddingClient()


def override_github_client():
    return FakeGitHubClient()


def override_coder_runner():
    return FakeCoderRunner(
        successful_searchbox_scenario
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
        get_coder_runner
    ] = override_coder_runner

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
        get_coder_runner,
        None,
    )


async def seed_plan(
    workspace_id: str,
    status: str = "approved",
) -> ExecutionPlan:
    output = valid_planner_output()

    async with TestAsyncSessionLocal() as db:
        plan = ExecutionPlan(
            workspace_id=workspace_id,
            repository_owner="acme",
            repository_name="storefront",
            issue_number=142,
            status=status,
            summary=output.summary,
            problem_analysis=(
                output.problem_analysis
            ),
            likely_root_cause=(
                output.likely_root_cause
            ),
            confidence=output.confidence,
            plan_json=output.model_dump(
                mode="json"
            ),
        )
        db.add(plan)
        await db.commit()
        await db.refresh(plan)

        return plan


async def cleanup_workspace(
    workspace_id: str,
) -> None:
    async with TestAsyncSessionLocal() as db:
        await db.execute(
            delete(ChangeSet).where(
                ChangeSet.workspace_id
                == workspace_id
            )
        )
        await db.execute(
            delete(ExecutionPlan).where(
                ExecutionPlan.workspace_id
                == workspace_id
            )
        )
        await db.commit()


async def dispose_database_engine() -> None:
    await test_engine.dispose()


def test_implement_plan_api_and_diff_endpoint():
    workspace_id = str(uuid.uuid4())
    workspace_path = (
        WORKSPACES_DIR / workspace_id
    )
    repo = workspace_path / "repository"
    create_coding_fixture_repo(repo)
    plan = asyncio.run(
        seed_plan(
            workspace_id
        )
    )

    try:
        with TestClient(app) as test_client:
            response = test_client.post(
                f"/api/v1/plans/{plan.id}/implement"
            )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "generated"
        assert body["tests_run"] is False
        assert body["files_changed"][0]["path"] == "src/components/SearchBox.tsx"
        assert body["lines_added"] > 0

        with TestClient(app) as test_client:
            diff_response = test_client.get(
                f"/api/v1/change-sets/{body['change_set_id']}/diff"
            )

        assert diff_response.status_code == 200
        diff_body = diff_response.json()
        assert diff_body["tests_run"] is False
        assert "searchProducts(debouncedQuery)" in diff_body["diff"]
    finally:
        asyncio.run(dispose_database_engine())
        asyncio.run(
            cleanup_workspace(
                workspace_id
            )
        )
        asyncio.run(dispose_database_engine())
        shutil.rmtree(
            workspace_path,
            ignore_errors=True,
        )


def test_implement_plan_api_uses_plan_workspace_only():
    workspace_a = str(uuid.uuid4())
    workspace_b = str(uuid.uuid4())
    workspace_a_path = (
        WORKSPACES_DIR / workspace_a
    )
    workspace_b_path = (
        WORKSPACES_DIR / workspace_b
    )
    repo_a = workspace_a_path / "repository"
    repo_b = workspace_b_path / "repository"
    create_coding_fixture_repo(repo_a)
    create_coding_fixture_repo(repo_b)
    plan = asyncio.run(
        seed_plan(
            workspace_a
        )
    )

    try:
        with TestClient(app) as test_client:
            response = test_client.post(
                f"/api/v1/plans/{plan.id}/implement"
            )

        assert response.status_code == 200
        assert "searchProducts(debouncedQuery)" in (
            repo_a / "src/components/SearchBox.tsx"
        ).read_text(encoding="utf-8")
        assert "searchProducts(query)" in (
            repo_b / "src/components/SearchBox.tsx"
        ).read_text(encoding="utf-8")
    finally:
        asyncio.run(dispose_database_engine())
        asyncio.run(
            cleanup_workspace(
                workspace_a
            )
        )
        asyncio.run(
            cleanup_workspace(
                workspace_b
            )
        )
        asyncio.run(dispose_database_engine())
        shutil.rmtree(
            workspace_a_path,
            ignore_errors=True,
        )
        shutil.rmtree(
            workspace_b_path,
            ignore_errors=True,
        )


def test_implement_plan_api_rejects_missing_and_unapproved_plans():
    workspace_id = str(uuid.uuid4())
    workspace_path = (
        WORKSPACES_DIR / workspace_id
    )
    repo = workspace_path / "repository"
    create_coding_fixture_repo(repo)
    pending_plan = asyncio.run(
        seed_plan(
            workspace_id,
            status="pending_approval",
        )
    )

    try:
        with TestClient(app) as test_client:
            missing = test_client.post(
                f"/api/v1/plans/{uuid.uuid4()}/implement"
            )
            unapproved = test_client.post(
                f"/api/v1/plans/{pending_plan.id}/implement"
            )

        assert missing.status_code == 404
        assert unapproved.status_code == 409
    finally:
        asyncio.run(dispose_database_engine())
        asyncio.run(
            cleanup_workspace(
                workspace_id
            )
        )
        asyncio.run(dispose_database_engine())
        shutil.rmtree(
            workspace_path,
            ignore_errors=True,
        )
