import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.db.models.change_set import (
    ChangeSet,
)
from app.db.models.execution_run import (
    ExecutionRun,
)
from app.observability.logging import (
    log_task_event,
    log_task_failure,
)
from app.services.sandbox.commands import (
    CommandPlan,
    build_command_plan,
)
from app.services.sandbox.detector import (
    detect_project,
)
from app.services.sandbox.docker import (
    DockerSandbox,
    SandboxExecutionError,
    SandboxHandle,
)
from app.services.sandbox.policy import (
    InvalidChangeSetStateError,
    WorkspaceStateMismatchError,
    validate_change_set_eligibility,
    validate_workspace_consistency,
)
from app.services.sandbox.results import (
    DEPENDENCY_INSTALL,
    EXECUTION_ERROR,
    EXECUTION_FAILED,
    EXECUTION_PASSED,
    EXECUTION_RUNNING,
    STATUS_ERROR,
    STATUS_FAIL,
    STATUS_SKIPPED,
    STATUS_TIMEOUT,
    CommandResult,
    ExecutionCommand,
    check_statuses,
    error_result,
    overall_status,
    skipped_result,
    timeout_result,
)
from app.services.tasks.failures import (
    classify_execution_failure,
)
from app.services.tasks.locking import (
    TaskOperationLockService,
)
from app.services.tasks.service import (
    TaskService,
)
from app.services.tasks.state_machine import (
    FAILED,
    TEST_FAILED,
    TESTING,
    VERIFICATION_PASSED,
)


class SandboxRuntime(Protocol):
    runtime_name: str

    def prepare(
        self,
        *,
        execution_run_id: uuid.UUID,
        source_repository: Path,
    ) -> SandboxHandle:
        ...

    def execute(
        self,
        *,
        handle: SandboxHandle,
        command: ExecutionCommand,
    ) -> CommandResult:
        ...

    def cleanup(
        self,
        handle: SandboxHandle | None,
    ) -> list[str]:
        ...


class ExecutionService:
    def __init__(
        self,
        *,
        sandbox: SandboxRuntime | None = None,
    ) -> None:
        self.sandbox = sandbox or DockerSandbox()

    async def get_execution_run(
        self,
        *,
        execution_run_id: uuid.UUID,
        db: AsyncSession,
    ) -> ExecutionRun | None:
        return await db.get(
            ExecutionRun,
            execution_run_id,
        )

    async def execute_change_set(
        self,
        *,
        change_set_id: uuid.UUID,
        repository_path: Path,
        db: AsyncSession,
        task_id: uuid.UUID | None = None,
        acquire_lock: bool = True,
    ) -> ExecutionRun:
        change_set = await db.get(
            ChangeSet,
            change_set_id,
            options=[
                selectinload(ChangeSet.files)
            ],
            populate_existing=True,
        )

        if change_set is None:
            raise LookupError(
                "ChangeSet not found"
            )

        validate_change_set_eligibility(
            change_set
        )
        validate_workspace_consistency(
            change_set=change_set,
            repository_path=repository_path,
        )

        task_id = task_id or change_set.task_id
        task_service = TaskService()
        lock_service = TaskOperationLockService()
        lock_acquired = False

        run = ExecutionRun(
            change_set_id=change_set.id,
            workspace_id=change_set.workspace_id,
            task_id=task_id,
            status=EXECUTION_RUNNING,
            started_at=datetime.now(UTC),
            commands_json=[],
            results_json=[],
            timed_out=False,
            sandbox_runtime=self.sandbox.runtime_name,
            runtime_metadata={
                "changed_files": [
                    file.path
                    for file in change_set.files
                ],
                "limits": resource_metadata(),
            },
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)

        try:
            if task_id is not None and acquire_lock:
                await lock_service.acquire(
                    task_id=task_id,
                    operation="testing",
                    db=db,
                )
                lock_acquired = True

            if task_id is not None:
                await task_service.transition_task(
                    task_id=task_id,
                    new_status=TESTING,
                    db=db,
                    event_type="sandbox.started",
                    active_change_set_id=change_set.id,
                    active_execution_run_id=run.id,
                    metadata={
                        "change_set_id": str(
                            change_set.id
                        ),
                        "execution_run_id": str(
                            run.id
                        ),
                    },
                )

            started_at = time.perf_counter()
            handle: SandboxHandle | None = None
            cleanup_errors: list[str] = []
            results: list[CommandResult] = []
            command_plan: CommandPlan | None = None

            try:
                handle = self.sandbox.prepare(
                    execution_run_id=run.id,
                    source_repository=repository_path,
                )
                detection = detect_project(
                    handle.repository_path
                )
                command_plan = build_command_plan(
                    detection
                )
                run.commands_json = [
                    command.to_json()
                    for command in command_plan.commands
                ]
                run.runtime_metadata = {
                    **(run.runtime_metadata or {}),
                    **command_plan.metadata,
                }
                results.extend(
                    command_plan.skipped_results
                )

                if (
                    command_plan.metadata.get(
                        "verification_mode"
                    )
                    == "skipped"
                ):
                    log_task_event(
                        "sandbox.verification_skipped",
                        task_id=(
                            str(task_id)
                            if task_id is not None
                            else None
                        ),
                        change_set_id=str(
                            change_set.id
                        ),
                        execution_run_id=str(
                            run.id
                        ),
                        reason=command_plan.metadata.get(
                            "verification_reason"
                        ),
                        project_types=(
                            command_plan.metadata.get(
                                "project_types",
                                [],
                            )
                        ),
                        skipped_checks=[
                            result.command_type
                            for result in (
                                command_plan.skipped_results
                            )
                        ],
                    )

                results.extend(
                    self.run_commands(
                        handle=handle,
                        commands=command_plan.commands,
                        started_at=started_at,
                    )
                )
            except Exception as exc:
                log_task_failure(
                    "sandbox.execution_failed",
                    exc,
                    task_id=(
                        str(task_id)
                        if task_id is not None
                        else None
                    ),
                    change_set_id=str(change_set.id),
                    execution_run_id=str(run.id),
                    sandbox_runtime=self.sandbox.runtime_name,
                )
                run.error_message = sanitize_error(
                    exc
                )
                run.status = EXECUTION_ERROR
            finally:
                cleanup_errors = self.sandbox.cleanup(
                    handle
                )

            run.duration_ms = (
                time.perf_counter() - started_at
            ) * 1000
            run.completed_at = datetime.now(UTC)

            if cleanup_errors:
                run.runtime_metadata = {
                    **(run.runtime_metadata or {}),
                    "cleanup_errors": cleanup_errors,
                }

                if run.status == EXECUTION_RUNNING:
                    run.status = EXECUTION_ERROR
                    run.error_message = (
                        "Sandbox cleanup failed"
                    )

            if run.status == EXECUTION_RUNNING:
                run.status = overall_status(
                    results
                )

            run.timed_out = (
                run.status == "timeout"
                or any(
                    result.status == STATUS_TIMEOUT
                    for result in results
                )
            )
            run.results_json = [
                result.to_json()
                for result in results
            ]
            checks = check_statuses(
                results
            )
            run.tests_status = checks["tests"]
            run.lint_status = checks["lint"]
            run.typecheck_status = checks["typecheck"]
            run.build_status = checks["build"]

            await db.commit()
            await db.refresh(run)

            if task_id is not None:
                await transition_task_for_execution_run(
                    task_service=task_service,
                    task_id=task_id,
                    run=run,
                    db=db,
                )

            return run
        finally:
            if lock_acquired and task_id is not None:
                await lock_service.release(
                    task_id=task_id,
                    operation="testing",
                    db=db,
                )

    def run_commands(
        self,
        *,
        handle: SandboxHandle,
        commands: list[ExecutionCommand],
        started_at: float,
    ) -> list[CommandResult]:
        results: list[CommandResult] = []

        for index, command in enumerate(
            commands
        ):
            if overall_timeout_exceeded(
                started_at
            ):
                results.append(
                    timeout_result(
                        command=command,
                        duration_ms=(
                            settings.sandbox_overall_timeout_seconds
                            * 1000
                        ),
                        stdout=None,
                        stderr=b"ExecutionRun timed out",
                    )
                )
                results.extend(
                    skip_remaining(
                        commands[
                            index + 1:
                        ],
                        "Skipped after overall timeout",
                    )
                )
                break

            try:
                result = self.sandbox.execute(
                    handle=handle,
                    command=command,
                )
            except SandboxExecutionError as exc:
                result = error_result(
                    command=command,
                    message=sanitize_error(
                        exc
                    ),
                )

            results.append(result)

            if should_stop_after_result(
                result
            ):
                results.extend(
                    skip_remaining(
                        commands[
                            index + 1:
                        ],
                        "Skipped after "
                        + result.status.lower(),
                    )
                )
                break

        return results


async def transition_task_for_execution_run(
    *,
    task_service: TaskService,
    task_id: uuid.UUID,
    run: ExecutionRun,
    db: AsyncSession,
) -> None:
    if run.status == EXECUTION_PASSED:
        await task_service.transition_task(
            task_id=task_id,
            new_status=VERIFICATION_PASSED,
            db=db,
            event_type="sandbox.passed",
            active_execution_run_id=run.id,
            metadata=execution_task_metadata(
                run
            )
        )
        return

    failure_category = classify_execution_failure(
        run
    )
    target_status = (
        TEST_FAILED
        if run.status == EXECUTION_FAILED
        else FAILED
    )
    await task_service.transition_task(
        task_id=task_id,
        new_status=target_status,
        db=db,
        event_type="sandbox.failed",
        failure_category=failure_category,
        last_error=run.error_message
        or failure_category,
        active_execution_run_id=run.id,
        metadata=execution_task_metadata(
            run
        ),
    )


def execution_task_metadata(
    run: ExecutionRun,
) -> dict:
    return {
        "execution_run_id": str(run.id),
        "change_set_id": str(
            run.change_set_id
        ),
        "status": run.status,
        "duration_ms": run.duration_ms,
        "checks": {
            "tests": run.tests_status,
            "lint": run.lint_status,
            "typecheck": run.typecheck_status,
            "build": run.build_status,
        },
        "timed_out": run.timed_out,
        "verification": {
            "mode": (
                run.runtime_metadata or {}
            ).get("verification_mode"),
            "reason": (
                run.runtime_metadata or {}
            ).get("verification_reason"),
        },
    }


def should_stop_after_result(
    result: CommandResult,
) -> bool:
    return (
        result.status
        in {
            STATUS_ERROR,
            STATUS_TIMEOUT,
        }
        or (
            result.command_type
            == DEPENDENCY_INSTALL
            and result.status
            == STATUS_FAIL
        )
    )


def skip_remaining(
    commands: list[ExecutionCommand],
    reason: str,
) -> list[CommandResult]:
    return [
        skipped_result(
            name=command.name,
            command_type=command.command_type,
            reason=reason,
        )
        for command in commands
        if command.command_type
        != DEPENDENCY_INSTALL
    ]


def overall_timeout_exceeded(
    started_at: float,
) -> bool:
    return (
        time.perf_counter() - started_at
    ) > settings.sandbox_overall_timeout_seconds


def resource_metadata() -> dict:
    return {
        "cpu_limit": settings.sandbox_cpu_limit,
        "memory_limit": settings.sandbox_memory_limit,
        "pids_limit": settings.sandbox_pids_limit,
        "command_timeout_seconds": (
            settings.sandbox_command_timeout_seconds
        ),
        "overall_timeout_seconds": (
            settings.sandbox_overall_timeout_seconds
        ),
        "install_network": (
            settings.sandbox_install_network
        ),
        "execution_network": (
            settings.sandbox_execution_network
        ),
        "stdout_max_bytes": (
            settings.sandbox_stdout_max_bytes
        ),
        "stderr_max_bytes": (
            settings.sandbox_stderr_max_bytes
        ),
    }


def sanitize_error(
    exc: Exception,
) -> str:
    return exc.__class__.__name__


def serialize_execution_run(
    run: ExecutionRun,
) -> dict:
    checks = {
        "tests": run.tests_status
        or STATUS_SKIPPED,
        "lint": run.lint_status
        or STATUS_SKIPPED,
        "typecheck": run.typecheck_status
        or STATUS_SKIPPED,
        "build": run.build_status
        or STATUS_SKIPPED,
    }

    return {
        "execution_run_id": str(run.id),
        "change_set_id": str(run.change_set_id),
        "workspace_id": run.workspace_id,
        "status": run.status,
        "checks": checks,
        "duration_ms": run.duration_ms,
        "commands": run.commands_json,
        "results": run.results_json,
        "timed_out": run.timed_out,
        "error_message": run.error_message,
    }
