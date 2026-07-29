import asyncio
import shutil
import uuid

from sqlalchemy import func, select

from app.core.config import settings
from app.db.models.change_set import ChangeSet
from app.db.models.debug_attempt import DebugAttempt
from app.db.models.execution_run import ExecutionRun
from app.db.session import AsyncSessionLocal
from app.db.session import engine
from app.services.changes.git import (
    get_base_commit_sha,
)
from app.services.debugging.orchestrator import (
    DebugOrchestrator,
)
from app.services.sandbox.results import (
    EXECUTION_ERROR,
    EXECUTION_FAILED,
    STATUS_ERROR,
    TEST,
)
from app.api.routes.indexing import WORKSPACES_DIR
from tests.coding_fixtures import (
    fixed_searchbox_content,
)
from tests.debugging_fixtures import (
    FakeDebuggerRunner,
    FakeExecutionService,
    RaisingDebuggerRunner,
    alternate_searchbox_content,
    failed_outcome,
    fixed_searchbox_scenario,
    no_change_scenario,
    passed_outcome,
    plan_revision_scenario,
    seed_execution_run,
    update_file_scenario,
    write_broken_searchbox,
)
from tests.execution_fixtures import (
    cleanup_execution_workspace,
    create_node_execution_fixture_repo,
    seed_generated_change_set,
)


def test_debugger_repairs_failed_run_and_reruns_step7():
    workspace = prepare_failed_workspace()
    head_before = get_base_commit_sha(
        workspace.repo
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
                workspace.workspace_id
            )
        ]
    )
    orchestrator = DebugOrchestrator(
        debugger_runner=debugger,
        execution_service=execution,
    )

    try:
        result = run_async(
            run_debug(
                orchestrator,
                workspace.failed_run.id,
                workspace.repo,
            )
        )
        attempts = run_async(
            load_debug_attempts(
                workspace.workspace_id
            )
        )
        change_sets = run_async(
            load_change_sets(
                workspace.workspace_id
            )
        )

        assert result.status == "passed"
        assert result.reason is None
        assert result.final_change_set_id != workspace.change_set.id
        assert len(result.attempts) == 1
        assert debugger.invocations == 1
        assert len(execution.calls) == 1

        attempt = attempts[0]
        child = [
            change_set
            for change_set in change_sets
            if change_set.id
            == attempt.new_change_set_id
        ][0]

        assert attempt.status == "passed"
        assert attempt.failure_category == "test_failure"
        assert attempt.retry_execution_run_id is not None
        assert attempt.diff_hash is not None
        assert attempt.failure_fingerprint is not None
        assert child.parent_change_set_id == workspace.change_set.id
        assert child.base_commit_sha == workspace.change_set.base_commit_sha
        assert (
            workspace.repo
            / "src/components/SearchBox.tsx"
        ).read_text(
            encoding="utf-8"
        ) == fixed_searchbox_content()
        assert get_base_commit_sha(
            workspace.repo
        ) == head_before
        assert str(workspace.repo) not in debugger.inputs[0]
    finally:
        cleanup_workspace(
            workspace
        )


def test_debug_workflow_preserves_chain_until_pass():
    workspace = prepare_failed_workspace()
    debugger = FakeDebuggerRunner(
        [
            fixed_searchbox_scenario(
                alternate_searchbox_content()
            ),
            fixed_searchbox_scenario(
                fixed_searchbox_content()
            ),
        ]
    )
    execution = FakeExecutionService(
        [
            failed_outcome(
                workspace.workspace_id
            ),
            passed_outcome(
                workspace.workspace_id
            ),
        ]
    )
    orchestrator = DebugOrchestrator(
        debugger_runner=debugger,
        execution_service=execution,
    )

    try:
        result = run_async(
            run_debug(
                orchestrator,
                workspace.failed_run.id,
                workspace.repo,
            )
        )
        attempts = run_async(
            load_debug_attempts(
                workspace.workspace_id
            )
        )
        change_sets = run_async(
            load_change_sets(
                workspace.workspace_id
            )
        )
        runs = run_async(
            load_execution_runs(
                workspace.workspace_id
            )
        )

        first_child = change_sets_by_parent(
            change_sets
        )[workspace.change_set.id][0]
        second_child = change_sets_by_parent(
            change_sets
        )[first_child.id][0]

        assert result.status == "passed"
        assert len(attempts) == 2
        assert len(change_sets) == 3
        assert len(runs) == 3
        assert first_child.parent_change_set_id == workspace.change_set.id
        assert second_child.parent_change_set_id == first_child.id
        assert {
            change_set.base_commit_sha
            for change_set in change_sets
        } == {
            workspace.change_set.base_commit_sha
        }
        assert attempts[0].status == "failed"
        assert attempts[1].status == "passed"
    finally:
        cleanup_workspace(
            workspace
        )


def test_plan_revision_stops_without_expanding_scope():
    workspace = prepare_failed_workspace()
    hook_before = (
        workspace.repo / "src/hooks/useDebounce.ts"
    ).read_text(
        encoding="utf-8"
    )
    debugger = FakeDebuggerRunner(
        [
            plan_revision_scenario
        ]
    )
    execution = FakeExecutionService(
        []
    )
    orchestrator = DebugOrchestrator(
        debugger_runner=debugger,
        execution_service=execution,
    )

    try:
        result = run_async(
            run_debug(
                orchestrator,
                workspace.failed_run.id,
                workspace.repo,
            )
        )
        attempts = run_async(
            load_debug_attempts(
                workspace.workspace_id
            )
        )

        assert result.status == "stopped"
        assert result.reason == "plan_revision_required"
        assert len(result.attempts) == 1
        assert debugger.invocations == 1
        assert execution.calls == []
        assert attempts[0].new_change_set_id is None
        assert attempts[0].retry_execution_run_id is None
        assert (
            workspace.repo / "src/hooks/useDebounce.ts"
        ).read_text(
            encoding="utf-8"
        ) == hook_before
    finally:
        cleanup_workspace(
            workspace
        )


def test_infrastructure_failure_never_invokes_debugger():
    workspace = prepare_failed_workspace(
        initial_status=EXECUTION_ERROR,
        result_status=STATUS_ERROR,
        stderr="Docker daemon unavailable",
        error_message="Docker daemon unavailable",
    )
    debugger = FakeDebuggerRunner(
        []
    )
    orchestrator = DebugOrchestrator(
        debugger_runner=debugger,
        execution_service=FakeExecutionService(
            []
        ),
    )

    try:
        result = run_async(
            run_debug(
                orchestrator,
                workspace.failed_run.id,
                workspace.repo,
            )
        )
        change_set_count = run_async(
            count_model(
                ChangeSet,
                workspace.workspace_id,
            )
        )

        assert result.status == "stopped"
        assert result.reason == "infrastructure_error"
        assert result.attempts == []
        assert debugger.invocations == 0
        assert change_set_count == 1
    finally:
        cleanup_workspace(
            workspace
        )


def test_max_attempts_are_enforced_by_backend(
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "debugger_max_attempts",
        2,
    )
    workspace = prepare_failed_workspace()
    debugger = FakeDebuggerRunner(
        [
            fixed_searchbox_scenario(
                alternate_searchbox_content()
            ),
            fixed_searchbox_scenario(
                fixed_searchbox_content()
            ),
        ]
    )
    execution = FakeExecutionService(
        [
            failed_outcome(
                workspace.workspace_id,
                stdout="FAIL attempt one still failing\n",
            ),
            failed_outcome(
                workspace.workspace_id,
                stdout="FAIL attempt two still failing\n",
            ),
        ]
    )
    orchestrator = DebugOrchestrator(
        debugger_runner=debugger,
        execution_service=execution,
    )

    try:
        result = run_async(
            run_debug(
                orchestrator,
                workspace.failed_run.id,
                workspace.repo,
            )
        )

        assert result.status == "stopped"
        assert result.reason == "max_debug_attempts_exceeded"
        assert len(result.attempts) == 2
        assert debugger.invocations == 2
        assert len(execution.calls) == 2
    finally:
        cleanup_workspace(
            workspace
        )


def test_identical_patch_stops_before_step7_rerun():
    workspace = prepare_failed_workspace()
    debugger = FakeDebuggerRunner(
        [
            no_change_scenario
        ]
    )
    execution = FakeExecutionService(
        []
    )
    orchestrator = DebugOrchestrator(
        debugger_runner=debugger,
        execution_service=execution,
    )

    try:
        result = run_async(
            run_debug(
                orchestrator,
                workspace.failed_run.id,
                workspace.repo,
            )
        )
        attempts = run_async(
            load_debug_attempts(
                workspace.workspace_id
            )
        )
        change_set_count = run_async(
            count_model(
                ChangeSet,
                workspace.workspace_id,
            )
        )

        assert result.status == "stopped"
        assert result.reason == "no_progress"
        assert len(result.attempts) == 1
        assert execution.calls == []
        assert change_set_count == 1
        assert attempts[0].stop_reason == "no_progress"
    finally:
        cleanup_workspace(
            workspace
        )


def test_repeated_patch_and_failure_pair_stops_without_third_attempt():
    workspace = prepare_failed_workspace()
    debugger = FakeDebuggerRunner(
        [
            fixed_searchbox_scenario(
                fixed_searchbox_content()
            ),
            no_change_scenario,
        ]
    )
    execution = FakeExecutionService(
        [
            failed_outcome(
                workspace.workspace_id
            )
        ]
    )
    orchestrator = DebugOrchestrator(
        debugger_runner=debugger,
        execution_service=execution,
    )

    try:
        result = run_async(
            run_debug(
                orchestrator,
                workspace.failed_run.id,
                workspace.repo,
            )
        )

        assert result.status == "stopped"
        assert result.reason == "no_progress"
        assert len(result.attempts) == 2
        assert debugger.invocations == 2
        assert len(execution.calls) == 1
    finally:
        cleanup_workspace(
            workspace
        )


def test_invalid_repair_rolls_back_prior_patch():
    workspace = prepare_failed_workspace()
    package_before = (
        workspace.repo / "package.json"
    ).read_text(
        encoding="utf-8"
    )
    debugger = FakeDebuggerRunner(
        [
            malicious_package_write_scenario
        ]
    )
    execution = FakeExecutionService(
        []
    )
    orchestrator = DebugOrchestrator(
        debugger_runner=debugger,
        execution_service=execution,
    )

    try:
        result = run_async(
            run_debug(
                orchestrator,
                workspace.failed_run.id,
                workspace.repo,
            )
        )
        change_set_count = run_async(
            count_model(
                ChangeSet,
                workspace.workspace_id,
            )
        )

        assert result.status == "stopped"
        assert result.reason == "patch_validation_failed"
        assert execution.calls == []
        assert change_set_count == 1
        assert (
            workspace.repo / "package.json"
        ).read_text(
            encoding="utf-8"
        ) == package_before
        assert (
            workspace.repo
            / "src/components/SearchBox.tsx"
        ).read_text(
            encoding="utf-8"
        ) == workspace.initial_patch
    finally:
        cleanup_workspace(
            workspace
        )


def test_debugger_execution_error_stops_safely():
    workspace = prepare_failed_workspace()
    debugger = RaisingDebuggerRunner(
        RuntimeError("max turns exceeded")
    )
    execution = FakeExecutionService(
        []
    )
    orchestrator = DebugOrchestrator(
        debugger_runner=debugger,
        execution_service=execution,
    )

    try:
        result = run_async(
            run_debug(
                orchestrator,
                workspace.failed_run.id,
                workspace.repo,
            )
        )
        attempts = run_async(
            load_debug_attempts(
                workspace.workspace_id
            )
        )

        assert result.status == "stopped"
        assert result.reason == "debugger_execution_failed"
        assert debugger.invocations == 1
        assert execution.calls == []
        assert attempts[0].stop_reason == "debugger_execution_failed"
    finally:
        cleanup_workspace(
            workspace
        )


def test_secure_editor_rejects_dependency_edit_before_execution():
    workspace = prepare_failed_workspace()
    debugger = FakeDebuggerRunner(
        [
            update_file_scenario(
                path="package.json",
                content='{"scripts": {}}\n',
            )
        ]
    )
    execution = FakeExecutionService(
        []
    )
    orchestrator = DebugOrchestrator(
        debugger_runner=debugger,
        execution_service=execution,
    )

    try:
        result = run_async(
            run_debug(
                orchestrator,
                workspace.failed_run.id,
                workspace.repo,
            )
        )

        assert result.status == "stopped"
        assert result.reason == "debugger_execution_failed"
        assert execution.calls == []
    finally:
        cleanup_workspace(
            workspace
        )


def malicious_package_write_scenario(
    editor,
    debugger_input: str,
    trace_metadata: dict[str, str],
):
    (
        editor.repository_path / "package.json"
    ).write_text(
        '{"scripts": {"test": "echo hacked"}}\n',
        encoding="utf-8",
    )

    return fixed_searchbox_scenario(
        fixed_searchbox_content()
    )(
        editor,
        debugger_input,
        trace_metadata,
    )


async def run_debug(
    orchestrator: DebugOrchestrator,
    failed_run_id: uuid.UUID,
    repo,
):
    async with AsyncSessionLocal() as db:
        return await orchestrator.debug_execution_run(
            execution_run_id=failed_run_id,
            repository_path=repo,
            db=db,
        )


class WorkspaceFixture:
    def __init__(
        self,
        *,
        workspace_id: str,
        workspace_path,
        repo,
        change_set,
        failed_run,
        initial_patch: str,
    ) -> None:
        self.workspace_id = workspace_id
        self.workspace_path = workspace_path
        self.repo = repo
        self.change_set = change_set
        self.failed_run = failed_run
        self.initial_patch = initial_patch


def prepare_failed_workspace(
    *,
    initial_status: str = EXECUTION_FAILED,
    result_status: str = "FAIL",
    command_type: str = TEST,
    stderr: str = "",
    error_message: str | None = None,
) -> WorkspaceFixture:
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
    initial_patch = (
        repo / "src/components/SearchBox.tsx"
    ).read_text(
        encoding="utf-8"
    )
    change_set = run_async(
        seed_generated_change_set(
            workspace_id=workspace_id,
            repo=repo,
        )
    )

    async def seed_initial_run():
        async with AsyncSessionLocal() as db:
            return await seed_execution_run(
                db=db,
                workspace_id=workspace_id,
                change_set_id=change_set.id,
                status=initial_status,
                command_type=command_type,
                result_status=result_status,
                stderr=stderr,
                error_message=error_message,
            )

    failed_run = run_async(
        seed_initial_run()
    )

    return WorkspaceFixture(
        workspace_id=workspace_id,
        workspace_path=workspace_path,
        repo=repo,
        change_set=change_set,
        failed_run=failed_run,
        initial_patch=initial_patch,
    )


async def load_debug_attempts(
    workspace_id: str,
) -> list[DebugAttempt]:
    async with AsyncSessionLocal() as db:
        result = await db.scalars(
            select(DebugAttempt)
            .where(
                DebugAttempt.workspace_id
                == workspace_id
            )
            .order_by(
                DebugAttempt.attempt_number
            )
        )

        return list(
            result
        )


async def load_change_sets(
    workspace_id: str,
) -> list[ChangeSet]:
    async with AsyncSessionLocal() as db:
        result = await db.scalars(
            select(ChangeSet)
            .where(
                ChangeSet.workspace_id
                == workspace_id
            )
            .order_by(
                ChangeSet.created_at
            )
        )

        return list(
            result
        )


async def load_execution_runs(
    workspace_id: str,
) -> list[ExecutionRun]:
    async with AsyncSessionLocal() as db:
        result = await db.scalars(
            select(ExecutionRun)
            .where(
                ExecutionRun.workspace_id
                == workspace_id
            )
            .order_by(
                ExecutionRun.created_at
            )
        )

        return list(
            result
        )


async def count_model(
    model,
    workspace_id: str,
) -> int:
    async with AsyncSessionLocal() as db:
        return await db.scalar(
            select(
                func.count()
            )
            .select_from(model)
            .where(
                model.workspace_id
                == workspace_id
            )
        )


def change_sets_by_parent(
    change_sets: list[ChangeSet],
) -> dict[uuid.UUID, list[ChangeSet]]:
    by_parent: dict[uuid.UUID, list[ChangeSet]] = {}

    for change_set in change_sets:
        if change_set.parent_change_set_id:
            by_parent.setdefault(
                change_set.parent_change_set_id,
                [],
            ).append(
                change_set
            )

    return by_parent


def cleanup_workspace(
    workspace: WorkspaceFixture,
) -> None:
    run_async(
        cleanup_execution_workspace(
            workspace.workspace_id
        )
    )
    shutil.rmtree(
        workspace.workspace_path,
        ignore_errors=True,
    )


async def dispose_database_engine() -> None:
    await engine.dispose()


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
