import uuid
import hashlib
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
from app.services.changes.snapshot import (
    rollback_workspace,
)
from app.services.changes.validator import (
    DiffLimitExceededError,
    UnauthorizedFileChangeError,
    validate_actual_changes,
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


def sha256_text(
    text: str,
) -> str:
    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()


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
    ) -> ChangeSet:
        if plan.status != "approved":
            raise PlanNotApprovedError(
                "Only approved plans can be implemented"
            )

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

        try:
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
                sha256_text(diff_summary.diff)
            )
            change_set.status = "generated"
            await db.commit()
            await db.refresh(
                change_set,
                attribute_names=["files"],
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
            return change_set

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
