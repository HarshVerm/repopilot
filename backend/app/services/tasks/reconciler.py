import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.change_set import ChangeSet
from app.db.models.debug_attempt import DebugAttempt
from app.db.models.execution_plan import ExecutionPlan
from app.db.models.execution_run import ExecutionRun
from app.db.models.final_review import FinalReview
from app.db.models.publication import Publication
from app.services.tasks.failures import (
    classify_execution_failure,
)
from app.services.tasks.service import TaskService
from app.services.tasks.state_machine import (
    COMPLETED,
    CODING,
    DEBUGGING,
    FAILED,
    PATCH_GENERATED,
    PLAN_APPROVED,
    PLAN_PENDING_APPROVAL,
    PLAN_REJECTED,
    PUBLISHING,
    REVIEW_APPROVED,
    REVIEW_PENDING,
    REVIEW_REJECTED,
    TEST_FAILED,
    TESTING,
    VERIFICATION_PASSED,
    TaskTransitionError,
)


STALE_STATE_THRESHOLDS = {
    "repository_preparing": timedelta(
        minutes=30
    ),
    "indexing": timedelta(
        minutes=30
    ),
    "retrieving": timedelta(
        minutes=10
    ),
    "planning": timedelta(
        minutes=20
    ),
    "coding": timedelta(
        minutes=45
    ),
    "testing": timedelta(
        minutes=45
    ),
    "debugging": timedelta(
        minutes=45
    ),
    "publishing": timedelta(
        minutes=20
    ),
}


class TaskReconciler:
    def __init__(
        self,
        *,
        task_service: TaskService | None = None,
    ) -> None:
        self.task_service = (
            task_service or TaskService()
        )

    async def reconcile_task(
        self,
        *,
        task_id: uuid.UUID,
        db: AsyncSession,
    ):
        task = await self.task_service.require_task(
            task_id=task_id,
            db=db,
        )
        evidence = await self.load_evidence(
            task_id=task_id,
            db=db,
        )
        target = classify_task_from_evidence(
            evidence
        )

        if target is None:
            await self.task_service.record_event(
                task_id=task_id,
                event_type="task.reconcile.noop",
                db=db,
                metadata={
                    "status": task.status
                },
                commit=True,
            )
            return task

        status, pointers, failure_category = target

        try:
            return await self.task_service.transition_task(
                task_id=task_id,
                new_status=status,
                db=db,
                event_type="task.reconciled",
                metadata={
                    "from_status": task.status,
                    "to_status": status,
                    "evidence": list(
                        pointers.keys()
                    ),
                },
                failure_category=failure_category,
                allow_reconcile=True,
                **pointers,
            )
        except TaskTransitionError:
            await self.task_service.record_event(
                task_id=task_id,
                event_type="task.reconcile.skipped",
                db=db,
                metadata={
                    "status": task.status,
                    "target_status": status,
                },
                commit=True,
            )
            return task

    async def record_stale_if_needed(
        self,
        *,
        task_id: uuid.UUID,
        db: AsyncSession,
        now: datetime | None = None,
    ) -> dict | None:
        task = await self.task_service.require_task(
            task_id=task_id,
            db=db,
        )
        stale = detect_stale_task(
            task,
            now=now,
        )

        if stale is None:
            return None

        await self.task_service.record_event(
            task_id=task_id,
            event_type="task.stale_detected",
            db=db,
            metadata=stale,
            commit=True,
        )
        return stale

    async def load_evidence(
        self,
        *,
        task_id: uuid.UUID,
        db: AsyncSession,
    ) -> dict:
        return {
            "publication": await latest(
                db,
                Publication,
                task_id,
            ),
            "review": await latest(
                db,
                FinalReview,
                task_id,
            ),
            "execution_run": await latest(
                db,
                ExecutionRun,
                task_id,
            ),
            "debug_attempt": await latest(
                db,
                DebugAttempt,
                task_id,
            ),
            "change_set": await latest(
                db,
                ChangeSet,
                task_id,
            ),
            "plan": await latest(
                db,
                ExecutionPlan,
                task_id,
            ),
        }


async def latest(
    db: AsyncSession,
    model,
    task_id: uuid.UUID,
):
    result = await db.scalars(
        select(model)
        .where(
            model.task_id == task_id
        )
        .order_by(
            model.created_at.desc()
        )
        .limit(1)
    )
    return result.first()


def detect_stale_task(
    task,
    *,
    now: datetime | None = None,
) -> dict | None:
    threshold = STALE_STATE_THRESHOLDS.get(
        task.status
    )

    if threshold is None:
        return None

    observed_at = (
        task.last_event_at
        or task.updated_at
        or task.started_at
    )

    if observed_at is None:
        return None

    current_time = now or datetime.now(
        UTC
    )
    age = current_time - observed_at

    if age <= threshold:
        return None

    return {
        "status": task.status,
        "age_seconds": int(
            age.total_seconds()
        ),
        "threshold_seconds": int(
            threshold.total_seconds()
        ),
    }


def classify_task_from_evidence(
    evidence: dict,
) -> tuple[str, dict, str | None] | None:
    publication = evidence.get(
        "publication"
    )
    if publication is not None:
        pointers = {
            "publication_id": publication.id
        }
        if publication.status == "published":
            return (
                COMPLETED,
                pointers,
                None,
            )
        if publication.status in {
            "publishing",
            "local_committed",
            "pushed",
            "partially_published",
        }:
            return (
                PUBLISHING,
                pointers,
                None,
            )
        if publication.status == "failed":
            return (
                FAILED,
                pointers,
                "github_publish_error",
            )

    review = evidence.get(
        "review"
    )
    if review is not None:
        pointers = {
            "active_review_id": review.id
        }
        if review.status == "approved":
            return (
                REVIEW_APPROVED,
                pointers,
                None,
            )
        if review.status == "pending_review":
            return (
                REVIEW_PENDING,
                pointers,
                None,
            )
        if review.status == "rejected":
            return (
                REVIEW_REJECTED,
                pointers,
                "review_rejected",
            )

    run = evidence.get(
        "execution_run"
    )
    if run is not None:
        pointers = {
            "active_execution_run_id": run.id
        }
        if run.status == "passed":
            return (
                VERIFICATION_PASSED,
                pointers,
                None,
            )
        if run.status == "running":
            return (
                TESTING,
                pointers,
                None,
            )
        if run.status == "failed":
            return (
                TEST_FAILED,
                pointers,
                classify_execution_failure(
                    run
                ),
            )
        if run.status in {
            "timeout",
            "error",
        }:
            return (
                FAILED,
                pointers,
                classify_execution_failure(
                    run
                ),
            )

    attempt = evidence.get(
        "debug_attempt"
    )
    if attempt is not None and attempt.status in {
        "pending",
        "diagnosing",
        "patching",
        "testing",
    }:
        return (
            DEBUGGING,
            {},
            None,
        )

    change_set = evidence.get(
        "change_set"
    )
    if change_set is not None:
        pointers = {
            "active_change_set_id": change_set.id
        }
        if change_set.status == "generated":
            return (
                PATCH_GENERATED,
                pointers,
                None,
            )
        if change_set.status == "generating":
            return (
                CODING,
                pointers,
                None,
            )
        if change_set.status in {
            "validation_failed",
            "failed",
        }:
            return (
                FAILED,
                pointers,
                "patch_policy_error",
            )

    plan = evidence.get(
        "plan"
    )
    if plan is not None:
        pointers = {
            "active_plan_id": plan.id
        }
        if plan.status == "approved":
            return (
                PLAN_APPROVED,
                pointers,
                None,
            )
        if plan.status == "pending_approval":
            return (
                PLAN_PENDING_APPROVAL,
                pointers,
                None,
            )
        if plan.status == "rejected":
            return (
                PLAN_REJECTED,
                pointers,
                "plan_revision_required",
            )

    return None
