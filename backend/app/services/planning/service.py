import uuid
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.execution_plan import ExecutionPlan
from app.schemas.planning import (
    PlannerOutput,
)
from app.services.planning.agent import (
    AgentsPlannerRunner,
    PlannerRunner,
)
from app.services.planning.input import (
    PlannerInputError,
    build_planner_input,
)
from app.services.planning.validation import (
    PlanValidationError,
    validate_planner_output,
)
from app.services.tasks.failures import (
    PLANNER_ERROR,
    PLANNER_VALIDATION_ERROR,
)
from app.services.tasks.service import (
    TaskService,
)
from app.services.tasks.state_machine import (
    PLAN_APPROVED,
    PLAN_PENDING_APPROVAL,
    PLAN_REJECTED,
    PLANNING,
)


class PlanningError(RuntimeError):
    pass


class PlanStateError(ValueError):
    pass


def issue_query_text(
    issue: dict,
) -> str:
    return (
        f"{issue.get('title', '')}\n\n"
        f"{issue.get('body') or ''}"
    ).strip()


def serialize_plan(
    plan: ExecutionPlan,
) -> dict:
    return {
        "plan_id": str(plan.id),
        "status": plan.status,
        "workspace_id": plan.workspace_id,
        "owner": plan.repository_owner,
        "repo": plan.repository_name,
        "issue_number": plan.issue_number,
        "plan": plan.plan_json,
        "rejection_reason": plan.rejection_reason,
        "metadata": {
            "model": plan.planner_model,
            "latency_ms": plan.planner_latency_ms,
            "input_tokens": plan.input_tokens,
            "output_tokens": plan.output_tokens,
            "total_tokens": plan.total_tokens,
            "trace_include_sensitive_data": (
                settings.planner_trace_include_sensitive_data
            ),
        },
    }


class PlannerService:
    def __init__(
        self,
        *,
        planner_runner: PlannerRunner | None = None,
    ) -> None:
        self.planner_runner = (
            planner_runner
            or AgentsPlannerRunner()
        )

    async def create_plan(
        self,
        *,
        workspace_id: str,
        repository_path: Path,
        owner: str,
        repo: str,
        issue: dict,
        context_pack: dict,
        db: AsyncSession,
        task_id: uuid.UUID | None = None,
    ) -> ExecutionPlan:
        task_service = TaskService()
        agent_run = None

        if task_id is not None:
            await task_service.transition_task(
                task_id=task_id,
                new_status=PLANNING,
                db=db,
                event_type="planning.started",
                metadata={
                    "workspace_id": workspace_id,
                    "repository": f"{owner}/{repo}",
                    "issue_number": issue.get(
                        "number"
                    ),
                },
            )
            agent_run = await task_service.start_agent_run(
                task_id=task_id,
                agent_type="planner",
                model=self.planner_runner.model,
                db=db,
                metadata={
                    "workspace_id": workspace_id
                },
            )

        try:
            planner_input = build_planner_input(
                owner=owner,
                repo=repo,
                issue=issue,
                context_pack=context_pack,
            )
        except PlannerInputError as exc:
            if task_id is not None:
                if agent_run is not None:
                    await task_service.complete_agent_run(
                        agent_run_id=agent_run.id,
                        db=db,
                        status="failed",
                        error_type=exc.__class__.__name__,
                        error_message=str(exc),
                    )
                await task_service.set_failure(
                    task_id=task_id,
                    db=db,
                    failure_category=PLANNER_ERROR,
                    error=exc,
                    event_type="planner.failed",
                )
            raise PlanningError(
                "Planner input could not be built"
            ) from exc

        try:
            run_result = await self.planner_runner.run(
                planner_input,
                trace_metadata={
                    "workspace_id": workspace_id,
                    "issue_number": str(
                        issue.get("number", "")
                    ),
                    "repository": f"{owner}/{repo}",
                    "agent": "RepoPilot Planner",
                    "model": self.planner_runner.model,
                },
            )
            output = PlannerOutput.model_validate(
                run_result.output
            )
        except (RuntimeError, ValidationError) as exc:
            if task_id is not None:
                if agent_run is not None:
                    await task_service.complete_agent_run(
                        agent_run_id=agent_run.id,
                        db=db,
                        status="failed",
                        error_type=exc.__class__.__name__,
                        error_message=str(exc),
                    )
                await task_service.set_failure(
                    task_id=task_id,
                    db=db,
                    failure_category=PLANNER_ERROR,
                    error=exc,
                    event_type="planner.failed",
                )
            raise PlanningError(
                "Planner did not return valid structured output"
            ) from exc

        try:
            await validate_planner_output(
                output=output,
                workspace_id=workspace_id,
                repository_path=repository_path,
                db=db,
            )
        except PlanValidationError as exc:
            if task_id is not None:
                if agent_run is not None:
                    await task_service.complete_agent_run(
                        agent_run_id=agent_run.id,
                        db=db,
                        status="failed",
                        latency_ms=run_result.latency_ms,
                        input_tokens=run_result.input_tokens,
                        output_tokens=(
                            run_result.output_tokens
                        ),
                        total_tokens=run_result.total_tokens,
                        error_type=exc.__class__.__name__,
                        error_message=str(exc),
                    )
                await task_service.set_failure(
                    task_id=task_id,
                    db=db,
                    failure_category=PLANNER_VALIDATION_ERROR,
                    error=exc,
                    event_type="planner.validation_failed",
                )
            raise

        plan = ExecutionPlan(
            workspace_id=workspace_id,
            task_id=task_id,
            repository_owner=owner,
            repository_name=repo,
            issue_number=int(
                issue["number"]
            ),
            status="pending_approval",
            summary=output.summary,
            problem_analysis=(
                output.problem_analysis
            ),
            likely_root_cause=(
                output.likely_root_cause
            ),
            confidence=output.confidence,
            plan_json=output.model_dump(
                mode="json"
            ),
            planner_model=self.planner_runner.model,
            planner_latency_ms=(
                run_result.latency_ms
            ),
            input_tokens=run_result.input_tokens,
            output_tokens=(
                run_result.output_tokens
            ),
            total_tokens=run_result.total_tokens,
        )
        db.add(plan)
        await db.commit()
        await db.refresh(plan)

        if task_id is not None and agent_run is not None:
            await task_service.complete_agent_run(
                agent_run_id=agent_run.id,
                db=db,
                status="completed",
                latency_ms=run_result.latency_ms,
                input_tokens=run_result.input_tokens,
                output_tokens=(
                    run_result.output_tokens
                ),
                total_tokens=run_result.total_tokens,
                plan_id=plan.id,
            )
            await task_service.transition_task(
                task_id=task_id,
                new_status=PLAN_PENDING_APPROVAL,
                db=db,
                event_type="plan.pending_approval",
                active_plan_id=plan.id,
                metadata={
                    "plan_id": str(plan.id)
                },
            )

        return plan

    async def get_plan(
        self,
        *,
        plan_id: uuid.UUID,
        db: AsyncSession,
    ) -> ExecutionPlan | None:
        return await db.get(
            ExecutionPlan,
            plan_id,
        )

    async def approve_plan(
        self,
        *,
        plan_id: uuid.UUID,
        db: AsyncSession,
    ) -> ExecutionPlan:
        plan = await self.get_plan(
            plan_id=plan_id,
            db=db,
        )

        if plan is None:
            raise KeyError(
                "plan not found"
            )

        if plan.status != "pending_approval":
            raise PlanStateError(
                "Only pending_approval plans can be approved"
            )

        plan.status = "approved"
        await db.commit()
        await db.refresh(plan)

        if plan.task_id is not None:
            await TaskService().transition_task(
                task_id=plan.task_id,
                new_status=PLAN_APPROVED,
                db=db,
                event_type="plan.approved",
                active_plan_id=plan.id,
                metadata={
                    "plan_id": str(plan.id)
                },
            )

        return plan

    async def reject_plan(
        self,
        *,
        plan_id: uuid.UUID,
        reason: str | None,
        db: AsyncSession,
    ) -> ExecutionPlan:
        plan = await self.get_plan(
            plan_id=plan_id,
            db=db,
        )

        if plan is None:
            raise KeyError(
                "plan not found"
            )

        if plan.status != "pending_approval":
            raise PlanStateError(
                "Only pending_approval plans can be rejected"
            )

        plan.status = "rejected"
        plan.rejection_reason = reason
        await db.commit()
        await db.refresh(plan)

        if plan.task_id is not None:
            await TaskService().transition_task(
                task_id=plan.task_id,
                new_status=PLAN_REJECTED,
                db=db,
                event_type="plan.rejected",
                active_plan_id=plan.id,
                metadata={
                    "plan_id": str(plan.id),
                    "reason": reason,
                },
            )

        return plan
