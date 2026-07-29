import asyncio
import shutil
import uuid

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.api.routes.indexing import WORKSPACES_DIR
from app.core.config import settings
from app.db.session import (
    AsyncSessionLocal,
    engine,
    get_db,
)
from app.main import app
from app.services.sandbox.results import (
    EXECUTION_PASSED,
    STATUS_PASS,
)
from tests.debugging_fixtures import (
    seed_execution_run,
)
from tests.execution_fixtures import (
    cleanup_execution_workspace,
    create_node_execution_fixture_repo,
    seed_generated_change_set,
)


test_engine = create_async_engine(
    settings.database_url,
    poolclass=NullPool,
)

TestAsyncSessionLocal = async_sessionmaker(
    bind=test_engine,
    expire_on_commit=False,
)


async def dispose_database_engine() -> None:
    await engine.dispose()


async def dispose_test_database_engine() -> None:
    await test_engine.dispose()


async def override_get_db():
    async with TestAsyncSessionLocal() as session:
        yield session


def test_review_api_create_get_and_approve():
    workspace = prepare_api_workspace()
    app.dependency_overrides[
        get_db
    ] = override_get_db

    try:
        with TestClient(app) as test_client:
            response = test_client.post(
                f"/api/v1/change-sets/{workspace['change_set_id']}/review"
            )
            assert response.status_code == 200
            body = response.json()
            assert body["status"] == "pending_review"
            assert body["issue"]["issue_number"] == 142
            assert body["changes"]["files"]
            assert body["verification"]["status"] == "passed"
            assert body["diff"]

            review_id = body["review_id"]
            get_response = test_client.get(
                f"/api/v1/reviews/{review_id}"
            )
            assert get_response.status_code == 200
            assert get_response.json()["review_id"] == review_id

            approve_response = test_client.post(
                f"/api/v1/reviews/{review_id}/approve"
            )

        assert approve_response.status_code == 200
        assert approve_response.json()["status"] == "approved"
        assert approve_response.json()["decision"] == "approved"
    finally:
        cleanup_api_workspace(
            workspace
        )


def test_review_api_rejects_with_reason():
    workspace = prepare_api_workspace()
    app.dependency_overrides[
        get_db
    ] = override_get_db

    try:
        with TestClient(app) as test_client:
            response = test_client.post(
                f"/api/v1/change-sets/{workspace['change_set_id']}/review"
            )
            assert response.status_code == 200
            review_id = response.json()[
                "review_id"
            ]

            reject_response = test_client.post(
                f"/api/v1/reviews/{review_id}/reject",
                json={
                    "reason": "Keep the debounce delay configurable."
                },
            )

        assert reject_response.status_code == 200
        body = reject_response.json()
        assert body["status"] == "rejected"
        assert body["decision"] == "rejected"
        assert body["rejection_reason"] == (
            "Keep the debounce delay configurable."
        )
    finally:
        cleanup_api_workspace(
            workspace
        )


def prepare_api_workspace() -> dict:
    workspace_id = str(
        uuid.uuid4()
    )
    workspace_path = (
        WORKSPACES_DIR / workspace_id
    )
    repo = workspace_path / "repository"
    create_node_execution_fixture_repo(
        repo
    )

    async def seed_records():
        change_set = await seed_generated_change_set(
            workspace_id=workspace_id,
            repo=repo,
        )

        async with AsyncSessionLocal() as db:
            execution_run = await seed_execution_run(
                db=db,
                workspace_id=workspace_id,
                change_set_id=change_set.id,
                status=EXECUTION_PASSED,
                result_status=STATUS_PASS,
            )

        await dispose_database_engine()

        return {
            "workspace_id": workspace_id,
            "workspace_path": workspace_path,
            "change_set_id": change_set.id,
            "execution_run_id": execution_run.id,
        }

    workspace = asyncio.run(
        seed_records()
    )

    return workspace


def cleanup_api_workspace(
    workspace: dict,
) -> None:
    app.dependency_overrides.pop(
        get_db,
        None,
    )
    async def cleanup_records():
        await cleanup_execution_workspace(
            workspace["workspace_id"]
        )
        await dispose_database_engine()

    asyncio.run(
        cleanup_records()
    )
    asyncio.run(
        dispose_test_database_engine()
    )
    shutil.rmtree(
        workspace["workspace_path"],
        ignore_errors=True,
    )
