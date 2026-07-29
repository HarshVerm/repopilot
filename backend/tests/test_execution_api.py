import asyncio
import shutil
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.api.routes.execution import (
    get_sandbox_runtime,
)
from app.api.routes.indexing import WORKSPACES_DIR
from app.core.config import settings
from app.db.session import (
    engine,
    get_db,
)
from app.main import app
from app.services.sandbox.results import (
    STATUS_PASS,
)
from tests.execution_fixtures import (
    FakeSandbox,
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


@pytest.fixture(autouse=True)
def clear_execution_overrides():
    app.dependency_overrides[
        get_db
    ] = override_get_db

    yield

    app.dependency_overrides.pop(
        get_db,
        None,
    )
    app.dependency_overrides.pop(
        get_sandbox_runtime,
        None,
    )


def test_execute_change_set_api_and_get_run(
    tmp_path,
):
    workspace_id = str(uuid.uuid4())
    workspace_path = (
        WORKSPACES_DIR / workspace_id
    )
    repo = workspace_path / "repository"
    create_node_execution_fixture_repo(repo)
    change_set = asyncio.run(
        seed_generated_change_set(
            workspace_id=workspace_id,
            repo=repo,
        )
    )
    asyncio.run(dispose_database_engine())

    def override_sandbox():
        return FakeSandbox(
            sandbox_root=tmp_path / "sandboxes"
        )

    app.dependency_overrides[
        get_sandbox_runtime
    ] = override_sandbox

    try:
        with TestClient(app) as test_client:
            response = test_client.post(
                f"/api/v1/change-sets/{change_set.id}/execute"
            )
            assert response.status_code == 200
            body = response.json()
            assert body["status"] == "passed"
            assert body["checks"]["tests"] == STATUS_PASS
            assert body["commands"]
            assert body["results"]

            get_response = test_client.get(
                f"/api/v1/execution-runs/{body['execution_run_id']}"
            )

            assert get_response.status_code == 200
            assert get_response.json()["execution_run_id"] == body["execution_run_id"]
    finally:
        asyncio.run(
            cleanup_execution_workspace(
                workspace_id
            )
        )
        asyncio.run(dispose_database_engine())
        asyncio.run(dispose_test_database_engine())
        shutil.rmtree(
            workspace_path,
            ignore_errors=True,
        )


def test_execute_change_set_api_rejects_missing_and_invalid_status(
    tmp_path,
):
    workspace_id = str(uuid.uuid4())
    workspace_path = (
        WORKSPACES_DIR / workspace_id
    )
    repo = workspace_path / "repository"
    create_node_execution_fixture_repo(repo)
    change_set = asyncio.run(
        seed_generated_change_set(
            workspace_id=workspace_id,
            repo=repo,
            status="validation_failed",
        )
    )
    asyncio.run(dispose_database_engine())

    def override_sandbox():
        return FakeSandbox(
            sandbox_root=tmp_path / "sandboxes"
        )

    app.dependency_overrides[
        get_sandbox_runtime
    ] = override_sandbox

    try:
        with TestClient(app) as test_client:
            missing = test_client.post(
                f"/api/v1/change-sets/{uuid.uuid4()}/execute"
            )
            invalid = test_client.post(
                f"/api/v1/change-sets/{change_set.id}/execute"
            )

        assert missing.status_code == 404
        assert invalid.status_code == 409
    finally:
        asyncio.run(
            cleanup_execution_workspace(
                workspace_id
            )
        )
        asyncio.run(dispose_database_engine())
        asyncio.run(dispose_test_database_engine())
        shutil.rmtree(
            workspace_path,
            ignore_errors=True,
        )
