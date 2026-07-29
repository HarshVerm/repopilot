import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.debugger.agent import (
    AgentsDebuggerRunner,
    DebuggerRunResult,
    DebuggerRunner,
)
from app.agents.debugger.service import (
    build_debugger_input,
)
from app.core.config import settings
from app.db.models.change_set import (
    ChangeSet,
    ChangeSetFile,
)
from app.db.models.debug_attempt import (
    DebugAttempt,
)
from app.db.models.execution_plan import (
    ExecutionPlan,
)
from app.db.models.execution_run import (
    ExecutionRun,
)
from app.schemas.debugging import (
    DebuggerOutput,
)
from app.services.changes.diff import (
    DiffSummary,
    summarize_diff,
)
from app.services.changes.editor import (
    PatchSecurityError,
    RepoPilotPatchEditor,
)
from app.services.changes.git import (
    get_git_status,
)
from app.services.changes.validator import (
    DiffLimitExceededError,
    UnauthorizedFileChangeError,
    validate_actual_changes,
)
from app.services.debugging.failure_classifier import (
    FailureClassification,
    classify_execution_run,
)
from app.services.debugging.fingerprint import (
    diff_hash,
    failure_fingerprint,
)
from app.services.debugging.policy import (
    DebugNotEligibleError,
    DebugPatchValidationError,
    DebuggerExecutionError,
    NoProgressError,
    PlanRevisionRequiredError,
    approved_files_from_plan,
    capture_patch_snapshot,
    restore_patch_snapshot,
    validate_debugger_scope,
)
from app.services.sandbox.manager import (
    ExecutionService,
)
from app.services.sandbox.results import (
    EXECUTION_PASSED,
)
from app.services.tasks.failures import (
    DEBUG_ATTEMPTS_EXHAUSTED,
    DEBUG_NO_PROGRESS,
    DEBUGGER_ERROR,
    PLAN_REVISION_REQUIRED,
)
from app.services.tasks.service import (
    TaskService,
)
from app.services.tasks.state_machine import (
    DEBUGGING,
    FAILED,
    TaskTransitionError,
    VERIFICATION_PASSED,
)


TERMINAL_NON_DEBUGGABLE_STATUSES = {
    "passed",
    "pending",
    "running",
}


@dataclass(frozen=True)
class DebugWorkflowResult:
    status: str
    reason: str | None
    attempts: list[DebugAttempt]
    final_change_set_id: uuid.UUID | None
    final_execution_run_id: uuid.UUID | None


class DebugOrchestrator:
    def __init__(
        self,
        *,
        debugger_runner: DebuggerRunner | None = None,
        execution_service: ExecutionService | None = None,
    ) -> None:
        self.debugger_runner = (
            debugger_runner
            or AgentsDebuggerRunner()
        )
        self.execution_service = (
            execution_service
            or ExecutionService()
        )

    async def get_debug_attempt(
        self,
        *,
        debug_attempt_id: uuid.UUID,
        db: AsyncSession,
    ) -> DebugAttempt | None:
        return await db.get(
            DebugAttempt,
            debug_attempt_id,
        )

    async def debug_execution_run(
        self,
        *,
        execution_run_id: uuid.UUID,
        repository_path: Path,
        db: AsyncSession,
        task_id: uuid.UUID | None = None,
    ) -> DebugWorkflowResult:
        current_run = await self.load_execution_run(
            execution_run_id,
            db,
        )

        if current_run.status in TERMINAL_NON_DEBUGGABLE_STATUSES:
            raise DebugNotEligibleError(
                "ExecutionRun is not eligible for debugging"
            )

        task_id = task_id or current_run.task_id
        task_service = TaskService()

        if task_id is not None:
            try:
                await task_service.transition_task(
                    task_id=task_id,
                    new_status=DEBUGGING,
                    db=db,
                    event_type="debugger.started",
                    active_execution_run_id=current_run.id,
                    metadata={
                        "execution_run_id": str(
                            current_run.id
                        )
                    },
                )
            except TaskTransitionError:
                await task_service.record_event(
                    task_id=task_id,
                    event_type="debugger.start_skipped",
                    db=db,
                    metadata={
                        "execution_run_id": str(
                            current_run.id
                        )
                    },
                    commit=True,
                )

        attempts: list[DebugAttempt] = []
        seen_pairs: set[tuple[str, str]] = set()
        final_change_set_id: uuid.UUID | None = (
            current_run.change_set_id
        )
        final_execution_run_id: uuid.UUID | None = (
            current_run.id
        )

        initial_change_set = await self.load_change_set(
            current_run.change_set_id,
            db,
        )
        initial_classification = classify_execution_run(
            current_run
        )

        if not initial_classification.eligible:
            return await self.finalize_task_debug_result(
                task_id=task_id,
                result=DebugWorkflowResult(
                    status="stopped",
                    reason=initial_classification.category,
                    attempts=[],
                    final_change_set_id=final_change_set_id,
                    final_execution_run_id=final_execution_run_id,
                ),
                db=db,
            )

        seen_pairs.add(
            (
                diff_hash(
                    initial_change_set.diff
                ),
                failure_fingerprint(
                    execution_run=current_run,
                    classification=initial_classification,
                ),
            )
        )

        for attempt_number in range(
            1,
            settings.debugger_max_attempts + 1,
        ):
            classification = classify_execution_run(
                current_run
            )

            if not classification.eligible:
                return await self.finalize_task_debug_result(
                    task_id=task_id,
                    result=DebugWorkflowResult(
                        status="stopped",
                        reason=classification.category,
                        attempts=attempts,
                        final_change_set_id=final_change_set_id,
                        final_execution_run_id=final_execution_run_id,
                    ),
                    db=db,
                )

            parent_change_set = await self.load_change_set(
                current_run.change_set_id,
                db,
            )
            plan = await self.load_plan(
                parent_change_set.plan_id,
                db,
            )
            attempt = await self.create_attempt(
                attempt_number=attempt_number,
                classification=classification,
                failure_run=current_run,
                parent_change_set=parent_change_set,
                db=db,
            )
            attempts.append(attempt)

            try:
                attempt_result = await self.run_attempt(
                    attempt=attempt,
                    attempt_number=attempt_number,
                    classification=classification,
                    failure_run=current_run,
                    parent_change_set=parent_change_set,
                    plan=plan,
                    repository_path=repository_path,
                    seen_pairs=seen_pairs,
                    db=db,
                )
            except NoProgressError:
                await self.stop_attempt(
                    attempt,
                    "no_progress",
                    db,
                )
                return await self.finalize_task_debug_result(
                    task_id=task_id,
                    result=DebugWorkflowResult(
                        status="stopped",
                        reason="no_progress",
                        attempts=attempts,
                        final_change_set_id=final_change_set_id,
                        final_execution_run_id=final_execution_run_id,
                    ),
                    db=db,
                )
            except PlanRevisionRequiredError as exc:
                await self.stop_attempt(
                    attempt,
                    "plan_revision_required",
                    db,
                    diagnosis=str(exc),
                )
                return await self.finalize_task_debug_result(
                    task_id=task_id,
                    result=DebugWorkflowResult(
                        status="stopped",
                        reason="plan_revision_required",
                        attempts=attempts,
                        final_change_set_id=final_change_set_id,
                        final_execution_run_id=final_execution_run_id,
                    ),
                    db=db,
                )
            except (
                PatchSecurityError,
                UnauthorizedFileChangeError,
                DiffLimitExceededError,
                DebugPatchValidationError,
            ) as exc:
                await self.stop_attempt(
                    attempt,
                    "patch_validation_failed",
                    db,
                    diagnosis=exc.__class__.__name__,
                )
                return await self.finalize_task_debug_result(
                    task_id=task_id,
                    result=DebugWorkflowResult(
                        status="stopped",
                        reason="patch_validation_failed",
                        attempts=attempts,
                        final_change_set_id=final_change_set_id,
                        final_execution_run_id=final_execution_run_id,
                    ),
                    db=db,
                )
            except DebuggerExecutionError as exc:
                await self.stop_attempt(
                    attempt,
                    "debugger_execution_failed",
                    db,
                    diagnosis=str(exc),
                )
                return await self.finalize_task_debug_result(
                    task_id=task_id,
                    result=DebugWorkflowResult(
                        status="stopped",
                        reason="debugger_execution_failed",
                        attempts=attempts,
                        final_change_set_id=final_change_set_id,
                        final_execution_run_id=final_execution_run_id,
                    ),
                    db=db,
                )

            current_run = attempt_result.retry_execution_run
            final_change_set_id = (
                attempt_result.new_change_set.id
            )
            final_execution_run_id = current_run.id

            if current_run.status == EXECUTION_PASSED:
                attempt.status = "passed"
                attempt.completed_at = datetime.now(
                    UTC
                )
                await db.commit()
                await db.refresh(attempt)

                return await self.finalize_task_debug_result(
                    task_id=task_id,
                    result=DebugWorkflowResult(
                        status="passed",
                        reason=None,
                        attempts=attempts,
                        final_change_set_id=final_change_set_id,
                        final_execution_run_id=final_execution_run_id,
                    ),
                    db=db,
                )

            retry_classification = classify_execution_run(
                current_run
            )

            if not retry_classification.eligible:
                attempt.status = "stopped"
                attempt.stop_reason = (
                    retry_classification.category
                )
                attempt.completed_at = datetime.now(
                    UTC
                )
                await db.commit()
                await db.refresh(attempt)

                return await self.finalize_task_debug_result(
                    task_id=task_id,
                    result=DebugWorkflowResult(
                        status="stopped",
                        reason=retry_classification.category,
                        attempts=attempts,
                        final_change_set_id=final_change_set_id,
                        final_execution_run_id=final_execution_run_id,
                    ),
                    db=db,
                )

            pair = (
                attempt.diff_hash or "",
                failure_fingerprint(
                    execution_run=current_run,
                    classification=retry_classification,
                ),
            )

            if pair in seen_pairs:
                attempt.status = "stopped"
                attempt.stop_reason = "no_progress"
                attempt.completed_at = datetime.now(
                    UTC
                )
                await db.commit()
                await db.refresh(attempt)

                return await self.finalize_task_debug_result(
                    task_id=task_id,
                    result=DebugWorkflowResult(
                        status="stopped",
                        reason="no_progress",
                        attempts=attempts,
                        final_change_set_id=final_change_set_id,
                        final_execution_run_id=final_execution_run_id,
                    ),
                    db=db,
                )

            seen_pairs.add(pair)
            attempt.status = "failed"
            attempt.completed_at = datetime.now(
                UTC
            )
            await db.commit()
            await db.refresh(attempt)

        return await self.finalize_task_debug_result(
            task_id=task_id,
            result=DebugWorkflowResult(
                status="stopped",
                reason="max_debug_attempts_exceeded",
                attempts=attempts,
                final_change_set_id=final_change_set_id,
                final_execution_run_id=final_execution_run_id,
            ),
            db=db,
        )

    async def finalize_task_debug_result(
        self,
        *,
        task_id: uuid.UUID | None,
        result: DebugWorkflowResult,
        db: AsyncSession,
    ) -> DebugWorkflowResult:
        if task_id is None:
            return result

        task_service = TaskService()
        metadata = {
            "debug_status": result.status,
            "reason": result.reason,
            "attempts": len(result.attempts),
            "final_change_set_id": (
                str(result.final_change_set_id)
                if result.final_change_set_id
                else None
            ),
            "final_execution_run_id": (
                str(result.final_execution_run_id)
                if result.final_execution_run_id
                else None
            ),
        }

        try:
            if result.status == "passed":
                await task_service.transition_task(
                    task_id=task_id,
                    new_status=VERIFICATION_PASSED,
                    db=db,
                    event_type="debugger.passed",
                    active_change_set_id=(
                        result.final_change_set_id
                    ),
                    active_execution_run_id=(
                        result.final_execution_run_id
                    ),
                    metadata=metadata,
                )
            else:
                category = debug_failure_category(
                    result.reason
                )
                await task_service.transition_task(
                    task_id=task_id,
                    new_status=FAILED,
                    db=db,
                    event_type="debugger.stopped",
                    failure_category=category,
                    last_error=(
                        result.reason or category
                    ),
                    active_change_set_id=(
                        result.final_change_set_id
                    ),
                    active_execution_run_id=(
                        result.final_execution_run_id
                    ),
                    metadata=metadata,
                )
        except TaskTransitionError:
            await task_service.record_event(
                task_id=task_id,
                event_type="debugger.finalize_skipped",
                db=db,
                metadata=metadata,
                commit=True,
            )

        return result

    async def run_attempt(
        self,
        *,
        attempt: DebugAttempt,
        attempt_number: int,
        classification: FailureClassification,
        failure_run: ExecutionRun,
        parent_change_set: ChangeSet,
        plan: ExecutionPlan,
        repository_path: Path,
        seen_pairs: set[tuple[str, str]],
        db: AsyncSession,
    ):
        approved_files = approved_files_from_plan(
            plan
        )
        snapshot = capture_patch_snapshot(
            repository_path
        )
        editor = RepoPilotPatchEditor(
            repository_path=repository_path,
            allowed_files=approved_files,
        )

        attempt.status = "diagnosing"
        await db.commit()
        await db.refresh(attempt)

        debugger_input = build_debugger_input(
            plan=plan,
            change_set=parent_change_set,
            execution_run=failure_run,
            classification=classification,
            editor=editor,
            attempt_number=attempt_number,
        )
        agent_run_id: uuid.UUID | None = None
        task_service = TaskService()

        if attempt.task_id is not None:
            agent_run = await task_service.start_agent_run(
                task_id=attempt.task_id,
                agent_type="debugger",
                model=self.debugger_runner.model,
                db=db,
                debug_attempt_id=attempt.id,
                metadata={
                    "debug_attempt_id": str(
                        attempt.id
                    ),
                    "attempt_number": attempt_number,
                },
            )
            agent_run_id = agent_run.id

        try:
            run_result = await self.debugger_runner.run(
                debugger_input,
                editor=editor,
                trace_metadata={
                    "debug_attempt_id": str(
                        attempt.id
                    ),
                    "attempt_number": str(
                        attempt_number
                    ),
                    "workspace_id": attempt.workspace_id,
                    "failed_execution_run_id": str(
                        failure_run.id
                    ),
                    "parent_change_set_id": str(
                        parent_change_set.id
                    ),
                    "model": self.debugger_runner.model,
                },
            )
        except Exception as exc:
            restore_patch_snapshot(
                repository_path=repository_path,
                snapshot=snapshot,
            )
            if (
                attempt.task_id is not None
                and agent_run_id is not None
            ):
                await task_service.complete_agent_run(
                    agent_run_id=agent_run_id,
                    db=db,
                    status="failed",
                    error_type=exc.__class__.__name__,
                    error_message=str(exc),
                    debug_attempt_id=attempt.id,
                )
            raise DebuggerExecutionError(
                exc.__class__.__name__
            ) from exc

        try:
            output = DebuggerOutput.model_validate(
                run_result.output
            )
        except (TypeError, ValidationError) as exc:
            restore_patch_snapshot(
                repository_path=repository_path,
                snapshot=snapshot,
            )
            if (
                attempt.task_id is not None
                and agent_run_id is not None
            ):
                await task_service.complete_agent_run(
                    agent_run_id=agent_run_id,
                    db=db,
                    status="failed",
                    error_type=exc.__class__.__name__,
                    error_message=str(exc),
                    debug_attempt_id=attempt.id,
                )
            raise DebuggerExecutionError(
                "Debugger did not return valid structured output"
            ) from exc

        self.apply_debugger_metadata(
            attempt,
            run_result,
            output,
        )

        if (
            attempt.task_id is not None
            and agent_run_id is not None
        ):
            await task_service.complete_agent_run(
                agent_run_id=agent_run_id,
                db=db,
                status="completed",
                latency_ms=run_result.latency_ms,
                input_tokens=run_result.input_tokens,
                output_tokens=run_result.output_tokens,
                total_tokens=run_result.total_tokens,
                tool_calls_count=(
                    run_result.patch_operations_requested
                ),
                debug_attempt_id=attempt.id,
            )

        if output.needs_plan_revision:
            restore_patch_snapshot(
                repository_path=repository_path,
                snapshot=snapshot,
            )
            raise PlanRevisionRequiredError(
                output.revision_reason
                or "Plan revision required"
            )

        try:
            validate_debugger_scope(
                output=output,
                approved_files=approved_files,
            )
        except PlanRevisionRequiredError:
            restore_patch_snapshot(
                repository_path=repository_path,
                snapshot=snapshot,
            )
            raise

        if not output.retry_recommended:
            restore_patch_snapshot(
                repository_path=repository_path,
                snapshot=snapshot,
            )
            raise PlanRevisionRequiredError(
                "Debugger did not recommend a source repair retry"
            )

        attempt.status = "patching"
        await db.commit()
        await db.refresh(attempt)

        if has_untracked_files(
            repository_path
        ):
            restore_patch_snapshot(
                repository_path=repository_path,
                snapshot=snapshot,
            )
            raise UnauthorizedFileChangeError(
                "Debugger created untracked files"
            )

        try:
            diff_summary = summarize_diff(
                repository_path
            )
            validate_actual_changes(
                repository_path=repository_path,
                allowed_files=approved_files,
                diff_summary=diff_summary,
            )
        except (
            UnauthorizedFileChangeError,
            DiffLimitExceededError,
            PatchSecurityError,
        ):
            restore_patch_snapshot(
                repository_path=repository_path,
                snapshot=snapshot,
            )
            raise
        new_diff_hash = diff_hash(
            diff_summary.diff
        )
        current_fingerprint = (
            attempt.failure_fingerprint or ""
        )

        if (
            new_diff_hash == snapshot.diff_hash
            and (
                new_diff_hash,
                current_fingerprint,
            )
            in seen_pairs
        ):
            restore_patch_snapshot(
                repository_path=repository_path,
                snapshot=snapshot,
            )
            raise NoProgressError(
                "Debugger produced an identical patch"
            )

        child_change_set = self.create_repair_change_set(
            parent_change_set=parent_change_set,
            diff_summary=diff_summary,
            run_result=run_result,
            output=output,
        )
        db.add(child_change_set)
        await db.commit()
        await db.refresh(
            child_change_set,
            attribute_names=["files"],
        )

        attempt.new_change_set_id = (
            child_change_set.id
        )
        attempt.diff_hash = new_diff_hash
        attempt.status = "testing"
        await db.commit()
        await db.refresh(attempt)

        try:
            retry_execution_run = await self.execution_service.execute_change_set(
                change_set_id=child_change_set.id,
                repository_path=repository_path,
                db=db,
                task_id=attempt.task_id,
                acquire_lock=False,
            )
        except TypeError as exc:
            message = str(exc)
            if (
                "acquire_lock" not in message
                and "task_id" not in message
            ):
                raise

            retry_execution_run = await self.execution_service.execute_change_set(
                change_set_id=child_change_set.id,
                repository_path=repository_path,
                db=db,
            )
        attempt.retry_execution_run_id = (
            retry_execution_run.id
        )
        await db.commit()
        await db.refresh(attempt)

        return AttemptRunResult(
            new_change_set=child_change_set,
            retry_execution_run=retry_execution_run,
        )

    def create_repair_change_set(
        self,
        *,
        parent_change_set: ChangeSet,
        diff_summary: DiffSummary,
        run_result: DebuggerRunResult,
        output: DebuggerOutput,
    ) -> ChangeSet:
        child = ChangeSet(
            workspace_id=parent_change_set.workspace_id,
            task_id=parent_change_set.task_id,
            plan_id=parent_change_set.plan_id,
            parent_change_set_id=(
                parent_change_set.id
            ),
            plan_version=(
                parent_change_set.plan_version
            ),
            approved_plan_json=(
                parent_change_set.approved_plan_json
            ),
            status="generated",
            base_commit_sha=(
                parent_change_set.base_commit_sha
            ),
            summary=output.diagnosis,
            diff=diff_summary.diff,
            diff_hash=diff_hash(
                diff_summary.diff
            ),
            files_changed=len(
                diff_summary.files
            ),
            lines_added=diff_summary.lines_added,
            lines_deleted=(
                diff_summary.lines_deleted
            ),
            before_tree_hash=(
                parent_change_set.before_tree_hash
            ),
            after_tree_hash=diff_hash(
                diff_summary.diff
            ),
            coder_model=self.debugger_runner.model,
            input_tokens=run_result.input_tokens,
            output_tokens=run_result.output_tokens,
            total_tokens=run_result.total_tokens,
            latency_ms=run_result.latency_ms,
            patch_operations_requested=(
                run_result.patch_operations_requested
            ),
            patch_operations_accepted=(
                run_result.patch_operations_accepted
            ),
            patch_operations_rejected=(
                run_result.patch_operations_rejected
            ),
        )

        for file in diff_summary.files:
            child.files.append(
                ChangeSetFile(
                    path=file.path,
                    before_sha256=(
                        file.before_sha256
                    ),
                    after_sha256=(
                        file.after_sha256
                    ),
                    lines_added=file.lines_added,
                    lines_deleted=(
                        file.lines_deleted
                    ),
                )
            )

        return child

    async def create_attempt(
        self,
        *,
        attempt_number: int,
        classification: FailureClassification,
        failure_run: ExecutionRun,
        parent_change_set: ChangeSet,
        db: AsyncSession,
    ) -> DebugAttempt:
        attempt = DebugAttempt(
            workspace_id=(
                parent_change_set.workspace_id
            ),
            task_id=(
                parent_change_set.task_id
                or failure_run.task_id
            ),
            plan_id=parent_change_set.plan_id,
            parent_change_set_id=(
                parent_change_set.id
            ),
            failed_execution_run_id=(
                failure_run.id
            ),
            attempt_number=attempt_number,
            status="pending",
            failure_category=(
                classification.category
            ),
            failure_fingerprint=(
                failure_fingerprint(
                    execution_run=failure_run,
                    classification=classification,
                )
            ),
            started_at=datetime.now(UTC),
        )
        db.add(attempt)
        await db.commit()
        await db.refresh(attempt)

        return attempt

    def apply_debugger_metadata(
        self,
        attempt: DebugAttempt,
        run_result: DebuggerRunResult,
        output: DebuggerOutput,
    ) -> None:
        attempt.diagnosis = output.diagnosis
        attempt.likely_root_cause = (
            output.likely_root_cause
        )
        attempt.confidence = output.confidence
        attempt.latency_ms = (
            run_result.latency_ms
        )
        attempt.input_tokens = (
            run_result.input_tokens
        )
        attempt.output_tokens = (
            run_result.output_tokens
        )
        attempt.total_tokens = (
            run_result.total_tokens
        )

    async def stop_attempt(
        self,
        attempt: DebugAttempt,
        reason: str,
        db: AsyncSession,
        *,
        diagnosis: str | None = None,
    ) -> None:
        attempt.status = "stopped"
        attempt.stop_reason = reason
        attempt.completed_at = datetime.now(
            UTC
        )

        if diagnosis and not attempt.diagnosis:
            attempt.diagnosis = diagnosis

        await db.commit()
        await db.refresh(attempt)

    async def load_execution_run(
        self,
        execution_run_id: uuid.UUID,
        db: AsyncSession,
    ) -> ExecutionRun:
        run = await db.get(
            ExecutionRun,
            execution_run_id,
        )

        if run is None:
            raise LookupError(
                "ExecutionRun not found"
            )

        return run

    async def load_change_set(
        self,
        change_set_id: uuid.UUID,
        db: AsyncSession,
    ) -> ChangeSet:
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

        return change_set

    async def load_plan(
        self,
        plan_id: uuid.UUID,
        db: AsyncSession,
    ) -> ExecutionPlan:
        plan = await db.get(
            ExecutionPlan,
            plan_id,
        )

        if plan is None:
            raise LookupError(
                "ExecutionPlan not found"
            )

        return plan


@dataclass(frozen=True)
class AttemptRunResult:
    new_change_set: ChangeSet
    retry_execution_run: ExecutionRun


def has_untracked_files(
    repository_path: Path,
) -> bool:
    return any(
        line.startswith("?? ")
        for line in get_git_status(
            repository_path
        ).splitlines()
    )


def debug_failure_category(
    reason: str | None,
) -> str:
    if reason == "no_progress":
        return DEBUG_NO_PROGRESS
    if reason == "max_debug_attempts_exceeded":
        return DEBUG_ATTEMPTS_EXHAUSTED
    if reason == "plan_revision_required":
        return PLAN_REVISION_REQUIRED
    if reason == "debugger_execution_failed":
        return DEBUGGER_ERROR

    return DEBUGGER_ERROR


def serialize_debug_attempt(
    attempt: DebugAttempt,
) -> dict:
    return {
        "debug_attempt_id": str(attempt.id),
        "attempt": attempt.attempt_number,
        "failure_category": (
            attempt.failure_category
        ),
        "status": attempt.status,
        "parent_change_set_id": str(
            attempt.parent_change_set_id
        ),
        "new_change_set_id": (
            str(attempt.new_change_set_id)
            if attempt.new_change_set_id
            else None
        ),
        "failed_execution_run_id": str(
            attempt.failed_execution_run_id
        ),
        "retry_execution_run_id": (
            str(attempt.retry_execution_run_id)
            if attempt.retry_execution_run_id
            else None
        ),
        "diagnosis": attempt.diagnosis,
        "stop_reason": attempt.stop_reason,
    }


def serialize_debug_attempt_detail(
    attempt: DebugAttempt,
) -> dict:
    return {
        **serialize_debug_attempt(attempt),
        "workspace_id": attempt.workspace_id,
        "plan_id": str(attempt.plan_id),
        "likely_root_cause": (
            attempt.likely_root_cause
        ),
        "confidence": attempt.confidence,
        "diff_hash": attempt.diff_hash,
        "failure_fingerprint": (
            attempt.failure_fingerprint
        ),
    }


def serialize_debug_workflow(
    result: DebugWorkflowResult,
) -> dict:
    return {
        "status": result.status,
        "reason": result.reason,
        "attempts": len(result.attempts),
        "final_change_set_id": (
            str(result.final_change_set_id)
            if result.final_change_set_id
            else None
        ),
        "final_execution_run_id": (
            str(result.final_execution_run_id)
            if result.final_execution_run_id
            else None
        ),
        "history": [
            serialize_debug_attempt(attempt)
            for attempt in result.attempts
        ],
    }
