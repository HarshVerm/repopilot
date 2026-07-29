import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.change_set import (
    ChangeSet,
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
from app.db.models.final_review import (
    FinalReview,
)
from app.services.changes.diff import (
    DiffSummary,
    summarize_diff,
)
from app.services.changes.git import (
    get_base_commit_sha,
)
from app.services.changes.hashing import (
    diff_hash,
)
from app.services.changes.policy import (
    is_dependency_manifest,
)
from app.services.sandbox.policy import (
    WorkspaceStateMismatchError,
    validate_workspace_consistency,
)
from app.services.sandbox.results import (
    EXECUTION_PASSED,
    STATUS_SKIPPED,
)


PENDING_REVIEW = "pending_review"
APPROVED = "approved"
REJECTED = "rejected"
SUPERSEDED = "superseded"


class ReviewNotEligibleError(ValueError):
    pass


class ReviewAlreadyExistsError(ValueError):
    pass


class ReviewIntegrityError(ValueError):
    pass


class ReviewStateError(ValueError):
    pass


class WorkspaceDriftError(ReviewIntegrityError):
    pass


class ExecutionMismatchError(ReviewIntegrityError):
    pass


class ReviewService:
    async def get_review(
        self,
        *,
        review_id: uuid.UUID,
        db: AsyncSession,
    ) -> FinalReview | None:
        return await db.get(
            FinalReview,
            review_id,
        )

    async def create_review(
        self,
        *,
        change_set_id: uuid.UUID,
        repository_path: Path,
        db: AsyncSession,
    ) -> FinalReview:
        change_set = await self.load_change_set(
            change_set_id,
            db,
        )
        plan = await self.load_plan(
            change_set.plan_id,
            db,
        )

        validate_plan_for_review(
            plan
        )
        validate_change_set_for_review(
            change_set
        )
        validate_workspace_relationships(
            plan=plan,
            change_set=change_set,
        )
        await self.require_final_change_set(
            change_set,
            db,
        )

        execution_run = await self.find_successful_execution_run(
            change_set,
            db,
        )
        validate_execution_for_review(
            change_set=change_set,
            execution_run=execution_run,
        )
        diff_summary = await self.verify_current_workspace(
            change_set=change_set,
            repository_path=repository_path,
            db=db,
            expected_diff_hash=change_set.diff_hash,
            allow_diff_hash_backfill=True,
        )
        current_diff_hash = diff_hash(
            diff_summary.diff
        )
        existing = await self.find_existing_review(
            change_set_id=change_set.id,
            base_commit_sha=change_set.base_commit_sha,
            current_diff_hash=current_diff_hash,
            db=db,
        )

        if existing and existing.status in {
            PENDING_REVIEW,
            APPROVED,
        }:
            return existing

        if existing and existing.status == REJECTED:
            raise ReviewAlreadyExistsError(
                "A rejected review already exists for this exact diff"
            )

        debug_history = await self.build_debug_history(
            final_change_set=change_set,
            db=db,
        )
        files = file_metadata(
            diff_summary
        )
        verification = verification_summary(
            execution_run
        )
        risk_summary = build_risk_summary(
            files=files,
            files_changed=len(
                diff_summary.files
            ),
            lines_added=diff_summary.lines_added,
            lines_deleted=diff_summary.lines_deleted,
            verification=verification,
            debug_history=debug_history,
        )

        review = FinalReview(
            workspace_id=change_set.workspace_id,
            plan_id=plan.id,
            change_set_id=change_set.id,
            execution_run_id=execution_run.id,
            status=PENDING_REVIEW,
            base_commit_sha=change_set.base_commit_sha,
            diff_hash=current_diff_hash,
            files_changed=len(
                diff_summary.files
            ),
            lines_added=diff_summary.lines_added,
            lines_deleted=diff_summary.lines_deleted,
            summary=change_set.summary,
            risk_summary=risk_summary,
            files_json=files,
            verification_json=verification,
            debug_history_json=debug_history,
            issue_json=issue_snapshot(
                plan
            ),
            plan_snapshot_json=plan_snapshot(
                plan
            ),
            diff=diff_summary.diff,
        )
        db.add(review)
        await db.commit()
        await db.refresh(review)

        return review

    async def approve_review(
        self,
        *,
        review_id: uuid.UUID,
        repository_path: Path,
        db: AsyncSession,
    ) -> FinalReview:
        review = await self.load_review(
            review_id,
            db,
        )

        if review.status != PENDING_REVIEW:
            raise ReviewStateError(
                "Only pending reviews can be approved"
            )

        await self.revalidate_review_integrity(
            review=review,
            repository_path=repository_path,
            db=db,
        )

        review.status = APPROVED
        review.decision = APPROVED
        review.reviewed_at = datetime.now(
            UTC
        )
        await db.commit()
        await db.refresh(review)

        return review

    async def reject_review(
        self,
        *,
        review_id: uuid.UUID,
        rejection_reason: str | None,
        db: AsyncSession,
    ) -> FinalReview:
        review = await self.load_review(
            review_id,
            db,
        )

        if review.status != PENDING_REVIEW:
            raise ReviewStateError(
                "Only pending reviews can be rejected"
            )

        review.status = REJECTED
        review.decision = REJECTED
        review.rejection_reason = (
            rejection_reason
        )
        review.reviewed_at = datetime.now(
            UTC
        )
        await db.commit()
        await db.refresh(review)

        return review

    async def revalidate_review_integrity(
        self,
        *,
        review: FinalReview,
        repository_path: Path,
        db: AsyncSession,
    ) -> None:
        change_set = await self.load_change_set(
            review.change_set_id,
            db,
        )
        plan = await self.load_plan(
            review.plan_id,
            db,
        )
        execution_run = await self.load_execution_run(
            review.execution_run_id,
            db,
        )

        validate_plan_for_review(
            plan
        )
        validate_change_set_for_review(
            change_set
        )
        validate_workspace_relationships(
            plan=plan,
            change_set=change_set,
            execution_run=execution_run,
            review=review,
        )
        validate_execution_for_review(
            change_set=change_set,
            execution_run=execution_run,
        )
        await self.require_final_change_set(
            change_set,
            db,
        )

        if review.base_commit_sha != change_set.base_commit_sha:
            raise ReviewIntegrityError(
                "Review base commit does not match ChangeSet"
            )

        await self.verify_current_workspace(
            change_set=change_set,
            repository_path=repository_path,
            db=db,
            expected_diff_hash=review.diff_hash,
            allow_diff_hash_backfill=False,
        )

    async def verify_current_workspace(
        self,
        *,
        change_set: ChangeSet,
        repository_path: Path,
        db: AsyncSession,
        expected_diff_hash: str | None,
        allow_diff_hash_backfill: bool,
    ) -> DiffSummary:
        current_base = get_base_commit_sha(
            repository_path
        )

        if current_base != change_set.base_commit_sha:
            raise WorkspaceDriftError(
                "Workspace base commit does not match review base"
            )

        try:
            validate_workspace_consistency(
                change_set=change_set,
                repository_path=repository_path,
            )
        except WorkspaceStateMismatchError as exc:
            raise WorkspaceDriftError(
                str(exc)
            ) from exc
        diff_summary = summarize_diff(
            repository_path
        )
        current_hash = diff_hash(
            diff_summary.diff
        )

        if expected_diff_hash is None:
            if not allow_diff_hash_backfill:
                raise ReviewIntegrityError(
                    "ChangeSet lacks a persisted diff hash"
                )

            change_set.diff_hash = current_hash
            await db.commit()
            await db.refresh(
                change_set,
                attribute_names=["files"],
            )
        elif current_hash != expected_diff_hash:
            raise WorkspaceDriftError(
                "Current workspace diff does not match reviewed diff"
            )

        return diff_summary

    async def find_successful_execution_run(
        self,
        change_set: ChangeSet,
        db: AsyncSession,
    ) -> ExecutionRun:
        result = await db.scalars(
            select(ExecutionRun)
            .where(
                ExecutionRun.change_set_id
                == change_set.id,
                ExecutionRun.workspace_id
                == change_set.workspace_id,
                ExecutionRun.status
                == EXECUTION_PASSED,
            )
            .order_by(
                ExecutionRun.created_at.desc()
            )
            .limit(1)
        )
        execution_run = result.first()

        if execution_run is None:
            raise ReviewNotEligibleError(
                "A passed ExecutionRun for this ChangeSet is required"
            )

        return execution_run

    async def require_final_change_set(
        self,
        change_set: ChangeSet,
        db: AsyncSession,
    ) -> None:
        child_id = await db.scalar(
            select(ChangeSet.id)
            .where(
                ChangeSet.workspace_id
                == change_set.workspace_id,
                ChangeSet.parent_change_set_id
                == change_set.id,
            )
            .limit(1)
        )

        if child_id:
            raise ReviewNotEligibleError(
                "Only the final ChangeSet in the ancestry chain can be reviewed"
            )

    async def find_existing_review(
        self,
        *,
        change_set_id: uuid.UUID,
        base_commit_sha: str,
        current_diff_hash: str,
        db: AsyncSession,
    ) -> FinalReview | None:
        result = await db.scalars(
            select(FinalReview)
            .where(
                FinalReview.change_set_id
                == change_set_id,
                FinalReview.base_commit_sha
                == base_commit_sha,
                FinalReview.diff_hash
                == current_diff_hash,
            )
            .order_by(
                FinalReview.created_at.desc()
            )
            .limit(1)
        )

        return result.first()

    async def build_debug_history(
        self,
        *,
        final_change_set: ChangeSet,
        db: AsyncSession,
    ) -> dict:
        chain_ids = await self.change_set_chain_ids(
            final_change_set,
            db,
        )
        result = await db.scalars(
            select(DebugAttempt)
            .where(
                DebugAttempt.workspace_id
                == final_change_set.workspace_id,
                or_(
                    DebugAttempt.parent_change_set_id.in_(
                        chain_ids
                    ),
                    DebugAttempt.new_change_set_id.in_(
                        chain_ids
                    ),
                ),
            )
            .order_by(
                DebugAttempt.attempt_number,
                DebugAttempt.created_at,
            )
        )
        attempts = list(
            result
        )

        return {
            "debug_attempts": len(
                attempts
            ),
            "history": [
                {
                    "debug_attempt_id": str(
                        attempt.id
                    ),
                    "attempt": (
                        attempt.attempt_number
                    ),
                    "failure_category": (
                        attempt.failure_category
                    ),
                    "status": attempt.status,
                    "parent_change_set_id": str(
                        attempt.parent_change_set_id
                    ),
                    "new_change_set_id": (
                        str(
                            attempt.new_change_set_id
                        )
                        if attempt.new_change_set_id
                        else None
                    ),
                    "retry_execution_run_id": (
                        str(
                            attempt.retry_execution_run_id
                        )
                        if attempt.retry_execution_run_id
                        else None
                    ),
                }
                for attempt in attempts
            ],
        }

    async def change_set_chain_ids(
        self,
        final_change_set: ChangeSet,
        db: AsyncSession,
    ) -> list[uuid.UUID]:
        chain_ids = [
            final_change_set.id
        ]
        parent_id = (
            final_change_set.parent_change_set_id
        )

        while parent_id:
            chain_ids.append(
                parent_id
            )
            parent = await db.get(
                ChangeSet,
                parent_id,
            )

            if parent is None:
                break

            parent_id = (
                parent.parent_change_set_id
            )

        return chain_ids

    async def load_review(
        self,
        review_id: uuid.UUID,
        db: AsyncSession,
    ) -> FinalReview:
        review = await db.get(
            FinalReview,
            review_id,
        )

        if review is None:
            raise LookupError(
                "FinalReview not found"
            )

        return review

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


def validate_plan_for_review(
    plan: ExecutionPlan,
) -> None:
    if plan.status != "approved":
        raise ReviewNotEligibleError(
            "Only approved ExecutionPlans can be reviewed"
        )


def validate_change_set_for_review(
    change_set: ChangeSet,
) -> None:
    if change_set.status != "generated":
        raise ReviewNotEligibleError(
            "Only generated ChangeSets can be reviewed"
        )


def validate_execution_for_review(
    *,
    change_set: ChangeSet,
    execution_run: ExecutionRun,
) -> None:
    if execution_run.change_set_id != change_set.id:
        raise ExecutionMismatchError(
            "ExecutionRun does not belong to the ChangeSet"
        )

    if execution_run.workspace_id != change_set.workspace_id:
        raise ExecutionMismatchError(
            "ExecutionRun workspace does not match ChangeSet"
        )

    if execution_run.status != EXECUTION_PASSED:
        raise ReviewNotEligibleError(
            "ExecutionRun must be passed before review"
        )


def validate_workspace_relationships(
    *,
    plan: ExecutionPlan,
    change_set: ChangeSet,
    execution_run: ExecutionRun | None = None,
    review: FinalReview | None = None,
) -> None:
    if change_set.workspace_id != plan.workspace_id:
        raise ReviewIntegrityError(
            "ChangeSet workspace does not match ExecutionPlan"
        )

    if change_set.plan_id != plan.id:
        raise ReviewIntegrityError(
            "ChangeSet plan does not match ExecutionPlan"
        )

    if execution_run:
        if (
            execution_run.workspace_id
            != change_set.workspace_id
        ):
            raise ExecutionMismatchError(
                "ExecutionRun workspace does not match ChangeSet"
            )

        if (
            execution_run.change_set_id
            != change_set.id
        ):
            raise ExecutionMismatchError(
                "ExecutionRun does not belong to ChangeSet"
            )

    if review:
        if (
            review.workspace_id
            != change_set.workspace_id
            or review.plan_id != plan.id
            or review.change_set_id
            != change_set.id
        ):
            raise ReviewIntegrityError(
                "FinalReview relationships do not match persisted records"
            )

        if execution_run and (
            review.execution_run_id
            != execution_run.id
        ):
            raise ExecutionMismatchError(
                "FinalReview execution does not match ExecutionRun"
            )


def file_metadata(
    diff_summary: DiffSummary,
) -> list[dict]:
    return [
        {
            "path": file.path,
            "change_type": "modified",
            "lines_added": file.lines_added,
            "lines_deleted": file.lines_deleted,
            "before_sha256": file.before_sha256,
            "after_sha256": file.after_sha256,
        }
        for file in diff_summary.files
    ]


def verification_summary(
    execution_run: ExecutionRun,
) -> dict:
    return {
        "execution_run_id": str(
            execution_run.id
        ),
        "status": execution_run.status,
        "checks": {
            "tests": execution_run.tests_status
            or STATUS_SKIPPED,
            "typecheck": (
                execution_run.typecheck_status
                or STATUS_SKIPPED
            ),
            "lint": execution_run.lint_status
            or STATUS_SKIPPED,
            "build": execution_run.build_status
            or STATUS_SKIPPED,
        },
        "duration_ms": execution_run.duration_ms,
        "results": [
            {
                "name": result.get("name"),
                "command_type": result.get(
                    "command_type"
                ),
                "status": result.get("status"),
                "exit_code": result.get(
                    "exit_code"
                ),
                "duration_ms": result.get(
                    "duration_ms"
                ),
            }
            for result in (
                execution_run.results_json or []
            )
        ],
    }


def build_risk_summary(
    *,
    files: list[dict],
    files_changed: int,
    lines_added: int,
    lines_deleted: int,
    verification: dict,
    debug_history: dict,
) -> str:
    dependency_files = [
        file["path"]
        for file in files
        if is_dependency_manifest(
            Path(file["path"])
        )
    ]
    checks = verification.get(
        "checks",
        {},
    )
    check_text = ", ".join(
        f"{name} {status}"
        for name, status in checks.items()
    )
    debug_attempts = debug_history.get(
        "debug_attempts",
        0,
    )
    parts = [
        f"{files_changed} file(s) changed",
        f"{lines_added} addition(s)",
        f"{lines_deleted} deletion(s)",
        f"verification: {check_text}",
        (
            f"{debug_attempts} debugger attempt(s)"
            if debug_attempts
            else "no debugger retries"
        ),
        (
            "dependency files changed: "
            + ", ".join(
                dependency_files
            )
            if dependency_files
            else "no dependency changes"
        ),
    ]

    return "; ".join(
        parts
    )


def issue_snapshot(
    plan: ExecutionPlan,
) -> dict:
    return {
        "repository_owner": (
            plan.repository_owner
        ),
        "repository_name": (
            plan.repository_name
        ),
        "issue_number": plan.issue_number,
    }


def plan_snapshot(
    plan: ExecutionPlan,
) -> dict:
    return {
        "plan_id": str(plan.id),
        "status": plan.status,
        "summary": plan.summary,
        "problem_analysis": (
            plan.problem_analysis
        ),
        "likely_root_cause": (
            plan.likely_root_cause
        ),
        "confidence": plan.confidence,
        "approved_plan": plan.plan_json,
    }


def serialize_final_review(
    review: FinalReview,
) -> dict:
    return {
        "review_id": str(review.id),
        "status": review.status,
        "issue": review.issue_json,
        "plan": review.plan_snapshot_json,
        "changes": {
            "change_set_id": str(
                review.change_set_id
            ),
            "summary": review.summary,
            "files_changed": (
                review.files_changed
            ),
            "lines_added": (
                review.lines_added
            ),
            "lines_deleted": (
                review.lines_deleted
            ),
            "files": review.files_json,
        },
        "verification": (
            review.verification_json
        ),
        "debug_history": (
            review.debug_history_json
        ),
        "risk_summary": review.risk_summary,
        "base_commit_sha": (
            review.base_commit_sha
        ),
        "diff_hash": review.diff_hash,
        "diff": review.diff,
        "diff_truncated": False,
        "full_diff_available": True,
        "created_at": isoformat(
            review.created_at
        ),
        "reviewed_at": isoformat(
            review.reviewed_at
        ),
        "decision": review.decision,
        "rejection_reason": (
            review.rejection_reason
        ),
    }


def serialize_review_decision(
    review: FinalReview,
) -> dict:
    return {
        "review_id": str(review.id),
        "status": review.status,
        "decision": review.decision,
        "reviewed_at": isoformat(
            review.reviewed_at
        ),
        "rejection_reason": (
            review.rejection_reason
        ),
    }


def isoformat(
    value,
) -> str | None:
    if value is None:
        return None

    return value.isoformat()
