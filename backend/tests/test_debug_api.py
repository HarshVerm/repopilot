import asyncio
import shutil
import uuid

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.api.routes.debugging import (
    get_debug_orchestrator,
)
from app.api.routes.indexing import WORKSPACES_DIR
from app.core.config import settings
from app.db.session import (
    AsyncSessionLocal,
    engine,
    get_db,
)
from app.main import app
from app.services.debugging.orchestrator import (
    DebugOrchestrator,
)
from tests.coding_fixtures import (
    fixed_searchbox_content,
)
from tests.debugging_fixtures import (
    FakeDebuggerRunner,
    FakeExecutionService,
    fixed_searchbox_scenario,
    passed_outcome,
    seed_execution_run,
    write_broken_searchbox,
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


def test_debug_endpoint_runs_workflow_and_gets_attempt():
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
    write_broken_searchbox(
        repo
    )
    change_set = run_async(
        seed_generated_change_set(
            workspace_id=workspace_id,
            repo=repo,
        )
    )
    failed_run = run_async(
        seed_run(
            workspace_id,
            change_set.id,
        )
    )
    debugger = FakeDebuggerRunner(
        [
            fixed_searchbox_scenario(
                fixed_searchbox_content()
            )
        ]
    )
    execution = FakeExecutionService(
        [
            passed_outcome(
                workspace_id
            )
        ]
    )

    def override_orchestrator():
        return DebugOrchestrator(
            debugger_runner=debugger,
            execution_service=execution,
        )

    app.dependency_overrides[
        get_db
    ] = override_get_db
    app.dependency_overrides[
        get_debug_orchestrator
    ] = override_orchestrator

    try:
        with TestClient(app) as test_client:
            response = test_client.post(
                f"/api/v1/execution-runs/{failed_run.id}/debug"
            )

            assert response.status_code == 200
            body = response.json()
            assert body["status"] == "passed"
            assert body["attempts"] == 1
            assert body["final_change_set_id"] != str(
                change_set.id
            )
            assert body["final_execution_run_id"] != str(
                failed_run.id
            )

            attempt_id = body["history"][0][
                "debug_attempt_id"
            ]
            attempt_response = test_client.get(
                f"/api/v1/debug-attempts/{attempt_id}"
            )

        assert attempt_response.status_code == 200
        attempt_body = attempt_response.json()
        assert attempt_body["status"] == "passed"
        assert attempt_body["failure_category"] == "test_failure"
        assert attempt_body["diff_hash"] is not None
        assert attempt_body["failure_fingerprint"] is not None
    finally:
        app.dependency_overrides.pop(
            get_db,
            None,
        )
        app.dependency_overrides.pop(
            get_debug_orchestrator,
            None,
        )
        run_async(
            cleanup_execution_workspace(
                workspace_id
            )
        )
        asyncio.run(
            dispose_test_database_engine()
        )
        shutil.rmtree(
            workspace_path,
            ignore_errors=True,
        )


def test_debug_endpoint_rejects_passed_run():
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
    change_set = run_async(
        seed_generated_change_set(
            workspace_id=workspace_id,
            repo=repo,
        )
    )
    passed_run = run_async(
        seed_run(
            workspace_id,
            change_set.id,
            status="passed",
            result_status="PASS",
        )
    )
    app.dependency_overrides[
        get_db
    ] = override_get_db

    try:
        with TestClient(app) as test_client:
            response = test_client.post(
                f"/api/v1/execution-runs/{passed_run.id}/debug"
            )

        assert response.status_code == 409
    finally:
        app.dependency_overrides.pop(
            get_db,
            None,
        )
        run_async(
            cleanup_execution_workspace(
                workspace_id
            )
        )
        asyncio.run(
            dispose_test_database_engine()
        )
        shutil.rmtree(
            workspace_path,
            ignore_errors=True,
        )


async def seed_run(
    workspace_id: str,
    change_set_id,
    *,
    status: str = "failed",
    result_status: str = "FAIL",
):
    async with AsyncSessionLocal() as db:
        return await seed_execution_run(
            db=db,
            workspace_id=workspace_id,
            change_set_id=change_set_id,
            status=status,
            result_status=result_status,
        )


def run_async(
    coroutine,
):
    result = asyncio.run(
        coroutine
    )
    asyncio.run(
        dispose_database_engine()
    )

    return result
