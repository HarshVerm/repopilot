import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent_run import AgentRun
from app.db.models.change_set import ChangeSet
from app.db.models.debug_attempt import DebugAttempt
from app.db.models.execution_run import ExecutionRun
from app.db.models.final_review import FinalReview
from app.db.models.publication import Publication
from app.db.models.task_event import TaskEvent
from app.observability.pricing import (
    ModelPricingService,
)
from app.services.sandbox.results import (
    STATUS_ERROR,
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_SKIPPED,
    STATUS_TIMEOUT,
)
from app.services.tasks.service import (
    serialize_agent_run,
)


class TaskMetricsService:
    def __init__(
        self,
        *,
        pricing_service: ModelPricingService | None = None,
    ) -> None:
        self.pricing_service = (
            pricing_service or ModelPricingService()
        )

    async def get_metrics(
        self,
        *,
        task_id: uuid.UUID,
        db: AsyncSession,
    ) -> dict[str, Any]:
        agent_runs = list(
            await db.scalars(
                select(AgentRun)
                .where(
                    AgentRun.task_id == task_id
                )
                .order_by(
                    AgentRun.started_at
                )
            )
        )
        change_sets = list(
            await db.scalars(
                select(ChangeSet).where(
                    ChangeSet.task_id == task_id
                )
            )
        )
        execution_runs = list(
            await db.scalars(
                select(ExecutionRun).where(
                    ExecutionRun.task_id == task_id
                )
            )
        )
        debug_attempts = list(
            await db.scalars(
                select(DebugAttempt).where(
                    DebugAttempt.task_id == task_id
                )
            )
        )
        reviews = list(
            await db.scalars(
                select(FinalReview).where(
                    FinalReview.task_id == task_id
                )
            )
        )
        publications = list(
            await db.scalars(
                select(Publication).where(
                    Publication.task_id == task_id
                )
            )
        )
        retrieval_events = list(
            await db.scalars(
                select(TaskEvent).where(
                    TaskEvent.task_id == task_id,
                    TaskEvent.event_type
                    == "retrieval.completed",
                )
            )
        )

        agent_totals = aggregate_agent_runs(
            agent_runs,
            self.pricing_service,
        )
        sandbox_totals = aggregate_execution_runs(
            execution_runs
        )
        change_totals = aggregate_change_sets(
            change_sets
        )
        retrieval_totals = aggregate_retrieval(
            retrieval_events
        )

        latest_publication = (
            publications[-1]
            if publications
            else None
        )

        return {
            "agents": agent_totals,
            "retrieval": retrieval_totals,
            "changes": change_totals,
            "sandbox": sandbox_totals,
            "debugging": {
                "attempts": len(
                    debug_attempts
                ),
                "passed": len(
                    [
                        attempt
                        for attempt in debug_attempts
                        if attempt.status
                        == "passed"
                    ]
                ),
                "stopped": len(
                    [
                        attempt
                        for attempt in debug_attempts
                        if attempt.status
                        == "stopped"
                    ]
                ),
            },
            "review": {
                "reviews": len(reviews),
                "approved": len(
                    [
                        review
                        for review in reviews
                        if review.status
                        == "approved"
                    ]
                ),
                "rejected": len(
                    [
                        review
                        for review in reviews
                        if review.status
                        == "rejected"
                    ]
                ),
            },
            "publication": (
                {
                    "publication_id": str(
                        latest_publication.id
                    ),
                    "status": (
                        latest_publication.status
                    ),
                    "branch_name": (
                        latest_publication.branch_name
                    ),
                    "commit_sha": (
                        latest_publication.commit_sha
                    ),
                    "pull_request_number": (
                        latest_publication.pull_request_number
                    ),
                    "pull_request_url": (
                        latest_publication.pull_request_url
                    ),
                }
                if latest_publication
                else None
            ),
        }


def aggregate_agent_runs(
    agent_runs: list[AgentRun],
    pricing_service: ModelPricingService,
) -> dict[str, Any]:
    by_type: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "runs": 0,
            "completed": 0,
            "failed": 0,
            "latency_ms": 0.0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "tool_calls_count": 0,
            "estimated_cost_usd": None,
        }
    )
    total_cost: float | None = None

    for run in agent_runs:
        bucket = by_type[run.agent_type]
        bucket["runs"] += 1
        if run.status == "completed":
            bucket["completed"] += 1
        if run.status == "failed":
            bucket["failed"] += 1
        bucket["latency_ms"] += (
            run.latency_ms or 0.0
        )
        bucket["input_tokens"] += (
            run.input_tokens or 0
        )
        bucket["output_tokens"] += (
            run.output_tokens or 0
        )
        bucket["total_tokens"] += (
            run.total_tokens or 0
        )
        bucket["tool_calls_count"] += (
            run.tool_calls_count or 0
        )
        cost = pricing_service.estimate_cost_usd(
            model=run.model,
            input_tokens=run.input_tokens,
            output_tokens=run.output_tokens,
        )
        if cost is not None:
            bucket["estimated_cost_usd"] = (
                bucket["estimated_cost_usd"]
                or 0.0
            ) + cost
            total_cost = (
                total_cost or 0.0
            ) + cost

    totals = {
        "runs": len(agent_runs),
        "latency_ms": sum(
            run.latency_ms or 0.0
            for run in agent_runs
        ),
        "input_tokens": sum(
            run.input_tokens or 0
            for run in agent_runs
        ),
        "output_tokens": sum(
            run.output_tokens or 0
            for run in agent_runs
        ),
        "total_tokens": sum(
            run.total_tokens or 0
            for run in agent_runs
        ),
        "tool_calls_count": sum(
            run.tool_calls_count or 0
            for run in agent_runs
        ),
        "estimated_cost_usd": total_cost,
    }

    return {
        "total": totals,
        "by_type": dict(by_type),
        "runs": [
            serialize_agent_run(run)
            for run in agent_runs
        ],
    }


def aggregate_change_sets(
    change_sets: list[ChangeSet],
) -> dict[str, int]:
    return {
        "change_sets": len(change_sets),
        "files_changed": sum(
            item.files_changed or 0
            for item in change_sets
        ),
        "lines_added": sum(
            item.lines_added or 0
            for item in change_sets
        ),
        "lines_deleted": sum(
            item.lines_deleted or 0
            for item in change_sets
        ),
        "patch_operations_requested": sum(
            item.patch_operations_requested or 0
            for item in change_sets
        ),
        "patch_operations_accepted": sum(
            item.patch_operations_accepted or 0
            for item in change_sets
        ),
        "patch_operations_rejected": sum(
            item.patch_operations_rejected or 0
            for item in change_sets
        ),
    }


def aggregate_execution_runs(
    runs: list[ExecutionRun],
) -> dict[str, Any]:
    command_counts = {
        STATUS_PASS: 0,
        STATUS_FAIL: 0,
        STATUS_TIMEOUT: 0,
        STATUS_ERROR: 0,
        STATUS_SKIPPED: 0,
    }
    duration_by_command_type: dict[str, float] = (
        defaultdict(float)
    )
    command_count_by_type: dict[str, int] = (
        defaultdict(int)
    )

    for run in runs:
        for result in run.results_json or []:
            status = result.get(
                "status"
            )
            if status in command_counts:
                command_counts[status] += 1
            command_type = result.get(
                "command_type",
                "unknown",
            )
            command_count_by_type[command_type] += 1
            duration_by_command_type[
                command_type
            ] += float(
                result.get(
                    "duration_ms",
                    0.0,
                )
                or 0.0
            )

    return {
        "runs": len(runs),
        "passed": len(
            [
                run
                for run in runs
                if run.status == "passed"
            ]
        ),
        "failed": len(
            [
                run
                for run in runs
                if run.status == "failed"
            ]
        ),
        "timeouts": len(
            [
                run
                for run in runs
                if run.status == "timeout"
                or run.timed_out
            ]
        ),
        "errors": len(
            [
                run
                for run in runs
                if run.status == "error"
            ]
        ),
        "duration_ms": sum(
            run.duration_ms or 0.0
            for run in runs
        ),
        "commands": {
            "statuses": command_counts,
            "count_by_type": dict(
                command_count_by_type
            ),
            "duration_ms_by_type": dict(
                duration_by_command_type
            ),
        },
    }


def aggregate_retrieval(
    events: list[TaskEvent],
) -> dict[str, Any]:
    return {
        "queries": len(events),
        "final_results": sum(
            int(
                (
                    event.metadata_json
                    or {}
                ).get(
                    "final_result_count",
                    0,
                )
                or 0
            )
            for event in events
        ),
        "context_tokens": sum(
            int(
                (
                    event.metadata_json
                    or {}
                ).get(
                    "context_token_count",
                    0,
                )
                or 0
            )
            for event in events
        ),
        "latency_ms": sum(
            float(
                (
                    event.metadata_json
                    or {}
                ).get(
                    "latency_ms",
                    0.0,
                )
                or 0.0
            )
            for event in events
        ),
    }

