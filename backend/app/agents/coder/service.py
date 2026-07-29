import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.coder.agent import (
    AgentsCoderRunner,
    CoderRunner,
)
from app.core.config import settings
from app.db.models.change_set import (
    ChangeSet,
    ChangeSetFile,
)
from app.db.models.execution_plan import ExecutionPlan
from app.schemas.changes import (
    CoderOutput,
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
    DirtyWorkspaceError,
    get_base_commit_sha,
    get_git_status,
    get_tree_hash,
    require_clean_workspace,
)
from app.services.changes.hashing import (
    diff_hash,
)
from app.services.changes.snapshot import (
    rollback_workspace,
)
from app.services.changes.validator import (
    DiffLimitExceededError,
    UnauthorizedFileChangeError,
    validate_actual_changes,
)
from app.services.tasks.failures import (
    CODER_ERROR,
    PATCH_POLICY_ERROR,
    PLAN_REVISION_REQUIRED,
)
from app.services.tasks.locking import (
    TaskOperationConflict,
    TaskOperationLockService,
)
from app.services.tasks.service import (
    TaskService,
)
from app.services.tasks.state_machine import (
    CODING,
    PATCH_GENERATED,
)


class PlanNotApprovedError(ValueError):
    pass


class CoderExecutionError(RuntimeError):
    pass


class PlanRevisionRequired(RuntimeError):
    pass


def allowed_files_from_plan(
    plan: ExecutionPlan,
) -> set[str]:
    plan_json = plan.plan_json or {}

    return {
        item["path"]
        for item in plan_json.get(
            "files_to_modify",
            [],
        )
        if item.get("path")
    }


def status_has_untracked_files(
    status_output: str,
) -> bool:
    return any(
        line.startswith("?? ")
        for line in status_output.splitlines()
    )


def serialize_change_set_file(
    file: ChangeSetFile,
) -> dict:
    return {
        "path": file.path,
        "before_sha256": file.before_sha256,
        "after_sha256": file.after_sha256,
        "lines_added": file.lines_added,
        "lines_deleted": file.lines_deleted,
    }


def serialize_change_set(
    change_set: ChangeSet,
) -> dict:
    return {
        "change_set_id": str(change_set.id),
        "plan_id": str(change_set.plan_id),
        "workspace_id": change_set.workspace_id,
        "status": change_set.status,
        "base_commit_sha": (
            change_set.base_commit_sha
        ),
        "summary": change_set.summary,
        "files_changed": [
            serialize_change_set_file(file)
            for file in change_set.files
        ],
        "lines_added": change_set.lines_added,
        "lines_deleted": (
            change_set.lines_deleted
        ),
        "tests_run": False,
        "revision_reason": (
            change_set.revision_reason
        ),
    }


def serialize_change_set_diff(
    change_set: ChangeSet,
) -> dict:
    return {
        "change_set_id": str(change_set.id),
        "plan_id": str(change_set.plan_id),
        "base_commit_sha": (
            change_set.base_commit_sha
        ),
        "files_changed": [
            serialize_change_set_file(file)
            for file in change_set.files
        ],
        "lines_added": change_set.lines_added,
        "lines_deleted": (
            change_set.lines_deleted
        ),
        "diff": change_set.diff,
        "tests_run": False,
    }


def build_coder_input(
    *,
    issue: dict,
    plan: ExecutionPlan,
    context_pack: dict,
    editor: RepoPilotPatchEditor,
) -> str:
    sections = [
        "GitHub Issue:",
        f"Number: {issue.get('number')}",
        f"Title: {issue.get('title', '')}",
        "Body:",
        str(issue.get("body") or ""),
        "",
        "Approved ExecutionPlan:",
        str(plan.plan_json),
        "",
        "Approved files that may be updated:",
        "\n".join(
            sorted(editor.allowed_files)
        ),
        "",
        "Retrieved Context Pack:",
        str(context_pack),
        "",
        "Current approved file contents:",
    ]

    for file_path in sorted(
        editor.allowed_files
    ):
        sections.extend(
            [
                f"File: {file_path}",
                editor.read_file(file_path),
                "",
            ]
        )

    return "\n".join(sections)


class CodingService:
    def __init__(
        self,
        *,
        coder_runner: CoderRunner | None = None,
    ) -> None:
        self.coder_runner = (
            coder_runner
            or AgentsCoderRunner()
        )

    async def get_change_set(
        self,
        *,
        change_set_id: uuid.UUID,
        db: AsyncSession,
    ) -> ChangeSet | None:
        return await db.get(
            ChangeSet,
            change_set_id,
            options=[
                selectinload(ChangeSet.files)
            ],
        )

    async def implement_plan(
        self,
        *,
        plan: ExecutionPlan,
        repository_path: Path,
        issue: dict,
        context_pack: dict,
        db: AsyncSession,
        task_id: uuid.UUID | None = None,
    ) -> ChangeSet:
        if plan.status != "approved":
            raise PlanNotApprovedError(
                "Only approved plans can be implemented"
            )

        task_id = task_id or plan.task_id
        task_service = TaskService()
        lock_service = TaskOperationLockService()
        lock_acquired = False
        agent_run_id: uuid.UUID | None = None

        require_clean_workspace(
            repository_path
        )
        base_commit_sha = get_base_commit_sha(
            repository_path
        )
        before_tree_hash = get_tree_hash(
            repository_path
        )
        allowed_files = allowed_files_from_plan(
            plan
        )

        editor = RepoPilotPatchEditor(
            repository_path=repository_path,
            allowed_files=allowed_files,
        )

        change_set = ChangeSet(
            workspace_id=plan.workspace_id,
            task_id=task_id,
            plan_id=plan.id,
            plan_version=1,
            approved_plan_json=plan.plan_json,
            status="generating",
            base_commit_sha=base_commit_sha,
            before_tree_hash=before_tree_hash,
            coder_model=self.coder_runner.model,
            files_changed=0,
            lines_added=0,
            lines_deleted=0,
            patch_operations_requested=0,
            patch_operations_accepted=0,
            patch_operations_rejected=0,
        )
        db.add(change_set)
        await db.commit()
        await db.refresh(
            change_set,
            attribute_names=["files"],
        )

        if task_id is not None:
            await lock_service.acquire(
                task_id=task_id,
                operation="coding",
                db=db,
            )
            lock_acquired = True
            await task_service.transition_task(
                task_id=task_id,
                new_status=CODING,
                db=db,
                event_type="coding.started",
                active_plan_id=plan.id,
                active_change_set_id=change_set.id,
                metadata={
                    "plan_id": str(plan.id),
                    "change_set_id": str(
                        change_set.id
                    ),
                    "workspace_id": plan.workspace_id,
                },
            )

        try:
            if task_id is not None:
                agent_run = await task_service.start_agent_run(
                    task_id=task_id,
                    agent_type="coder",
                    model=self.coder_runner.model,
                    db=db,
                    plan_id=plan.id,
                    change_set_id=change_set.id,
                    metadata={
                        "change_set_id": str(
                            change_set.id
                        )
                    },
                )
                agent_run_id = agent_run.id

            coder_input = build_coder_input(
                issue=issue,
                plan=plan,
                context_pack=context_pack,
                editor=editor,
            )
            run_result = await self.coder_runner.run(
                coder_input,
                editor=editor,
                trace_metadata={
                    "change_set_id": str(
                        change_set.id
                    ),
                    "plan_id": str(plan.id),
                    "workspace_id": plan.workspace_id,
                    "agent": "RepoPilot Coder",
                    "model": self.coder_runner.model,
                },
            )
            output = CoderOutput.model_validate(
                run_result.output
            )
            self.apply_run_metadata(
                change_set,
                run_result,
                output,
            )

            if output.needs_plan_revision:
                rollback_workspace(
                    repository_path
                )
                change_set.status = "failed"
                change_set.revision_reason = (
                    output.revision_reason
                    or "Plan revision required"
                )
                change_set.diagnostics = {
                    "reason": "needs_plan_revision"
                }
                await db.commit()
                await db.refresh(
                    change_set,
                    attribute_names=["files"],
                )
                if (
                    task_id is not None
                    and agent_run_id is not None
                ):
                    await task_service.complete_agent_run(
                        agent_run_id=agent_run_id,
                        db=db,
                        status="completed",
                        latency_ms=run_result.latency_ms,
                        input_tokens=run_result.input_tokens,
                        output_tokens=(
                            run_result.output_tokens
                        ),
                        total_tokens=run_result.total_tokens,
                        tool_calls_count=(
                            run_result.patch_operations_requested
                        ),
                        change_set_id=change_set.id,
                    )
                    await task_service.set_failure(
                        task_id=task_id,
                        db=db,
                        failure_category=PLAN_REVISION_REQUIRED,
                        error=change_set.revision_reason
                        or "Plan revision required",
                        event_type="coder.plan_revision_required",
                        metadata={
                            "change_set_id": str(
                                change_set.id
                            )
                        },
                    )
                return change_set

            status = get_git_status(
                repository_path
            )

            if status_has_untracked_files(
                status
            ):
                raise UnauthorizedFileChangeError(
                    "Creating files is disabled in Step 6"
                )

            diff_summary = summarize_diff(
                repository_path
            )
            validate_actual_changes(
                repository_path=repository_path,
                allowed_files=allowed_files,
                diff_summary=diff_summary,
            )
            self.persist_generated_diff(
                change_set,
                diff_summary,
            )
            change_set.after_tree_hash = (
                diff_hash(diff_summary.diff)
            )
            change_set.diff_hash = diff_hash(
                diff_summary.diff
            )
            change_set.status = "generated"
            await db.commit()
            await db.refresh(
                change_set,
                attribute_names=["files"],
            )
            if (
                task_id is not None
                and agent_run_id is not None
            ):
                await task_service.complete_agent_run(
                    agent_run_id=agent_run_id,
                    db=db,
                    status="completed",
                    latency_ms=run_result.latency_ms,
                    input_tokens=run_result.input_tokens,
                    output_tokens=(
                        run_result.output_tokens
                    ),
                    total_tokens=run_result.total_tokens,
                    tool_calls_count=(
                        run_result.patch_operations_requested
                    ),
                    change_set_id=change_set.id,
                )
                await task_service.transition_task(
                    task_id=task_id,
                    new_status=PATCH_GENERATED,
                    db=db,
                    event_type="patch.generated",
                    active_change_set_id=change_set.id,
                    metadata={
                        "change_set_id": str(
                            change_set.id
                        ),
                        "files_changed": (
                            change_set.files_changed
                        ),
                        "lines_added": (
                            change_set.lines_added
                        ),
                        "lines_deleted": (
                            change_set.lines_deleted
                        ),
                    },
                )
            return change_set
        except (
            PatchSecurityError,
            UnauthorizedFileChangeError,
            DiffLimitExceededError,
        ) as exc:
            await self.mark_validation_failed(
                change_set,
                repository_path,
                str(exc),
                db,
            )
            if (
                task_id is not None
                and agent_run_id is not None
            ):
                await task_service.complete_agent_run(
                    agent_run_id=agent_run_id,
                    db=db,
                    status="completed",
                    error_type=exc.__class__.__name__,
                    error_message=str(exc),
                    change_set_id=change_set.id,
                )
                await task_service.set_failure(
                    task_id=task_id,
                    db=db,
                    failure_category=PATCH_POLICY_ERROR,
                    error=exc,
                    event_type="patch.validation_failed",
                    metadata={
                        "change_set_id": str(
                            change_set.id
                        )
                    },
                )
            return change_set
        except Exception as exc:
            rollback_workspace(
                repository_path
            )
            change_set.status = "failed"
            change_set.diagnostics = {
                "error": exc.__class__.__name__
            }
            await db.commit()
            await db.refresh(
                change_set,
                attribute_names=["files"],
            )
            if (
                task_id is not None
                and agent_run_id is not None
            ):
                await task_service.complete_agent_run(
                    agent_run_id=agent_run_id,
                    db=db,
                    status="failed",
                    error_type=exc.__class__.__name__,
                    error_message=str(exc),
                    change_set_id=change_set.id,
                )
            if task_id is not None:
                await task_service.set_failure(
                    task_id=task_id,
                    db=db,
                    failure_category=CODER_ERROR,
                    error=exc,
                    event_type="coder.failed",
                    metadata={
                        "change_set_id": str(
                            change_set.id
                        )
                    },
                )
            return change_set
        finally:
            if lock_acquired and task_id is not None:
                await lock_service.release(
                    task_id=task_id,
                    operation="coding",
                    db=db,
                )

    def apply_run_metadata(
        self,
        change_set: ChangeSet,
        run_result,
        output: CoderOutput,
    ) -> None:
        change_set.summary = output.summary
        change_set.latency_ms = (
            run_result.latency_ms
        )
        change_set.input_tokens = (
            run_result.input_tokens
        )
        change_set.output_tokens = (
            run_result.output_tokens
        )
        change_set.total_tokens = (
            run_result.total_tokens
        )
        change_set.patch_operations_requested = (
            run_result.patch_operations_requested
        )
        change_set.patch_operations_accepted = (
            run_result.patch_operations_accepted
        )
        change_set.patch_operations_rejected = (
            run_result.patch_operations_rejected
        )

    def persist_generated_diff(
        self,
        change_set: ChangeSet,
        diff_summary: DiffSummary,
    ) -> None:
        change_set.diff = diff_summary.diff
        change_set.files_changed = len(
            diff_summary.files
        )
        change_set.lines_added = (
            diff_summary.lines_added
        )
        change_set.lines_deleted = (
            diff_summary.lines_deleted
        )

        change_set.files.clear()

        for file in diff_summary.files:
            change_set.files.append(
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

    async def mark_validation_failed(
        self,
        change_set: ChangeSet,
        repository_path: Path,
        reason: str,
        db: AsyncSession,
    ) -> None:
        try:
            diff_summary = summarize_diff(
                repository_path
            )
            self.persist_generated_diff(
                change_set,
                diff_summary,
            )
        except Exception:
            change_set.diff = None

        rollback_workspace(
            repository_path
        )

        if get_git_status(
            repository_path
        ).strip():
            change_set.status = "failed"
            change_set.diagnostics = {
                "error": "rollback_failed",
                "reason": reason,
            }
        else:
            change_set.status = (
                "validation_failed"
            )
            change_set.diagnostics = {
                "reason": reason
            }

        await db.commit()
        await db.refresh(
            change_set,
            attribute_names=["files"],
        )
