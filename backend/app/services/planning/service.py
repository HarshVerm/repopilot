import re
import uuid
from pathlib import Path

from openai import OpenAIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.configuration import (
    AgentConfigurationError,
)
from app.core.config import settings
from app.db.models.execution_plan import ExecutionPlan
from app.observability.logging import (
    log_task_event,
    log_task_failure,
)
from app.schemas.planning import (
    ImplementationStep,
    PlannedFile,
    PlannerOutput,
    TestPlanItem,
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
    PLAN_REVISION_REQUIRED,
    PLANNING,
)


class PlanningError(RuntimeError):
    pass


class PlanStateError(ValueError):
    pass


SIMPLE_TEST_FILE_REQUEST_RE = re.compile(
    r"\b(?:add|create|make)\b.{0,80}"
    r"\b(?:a\s+|one\s+)?(?:new\s+)?test\s+file\b",
    re.IGNORECASE | re.DOTALL,
)
TEST_FRAMEWORK_REQUEST_RE = re.compile(
    r"\b(?:pytest|unittest|jest|vitest|mocha|jasmine|"
    r"playwright|cypress|unit\s+test|integration\s+test|"
    r"end[- ]to[- ]end|e2e)\b",
    re.IGNORECASE,
)


def apply_safe_planning_defaults(
    *,
    output: PlannerOutput,
    issue: dict,
    user_instructions: str | None = None,
) -> PlannerOutput:
    """Resolve only the narrow, safe form of an explicit plain test-file request."""

    if (
        not output.needs_more_context
        or output.files_to_modify
    ):
        return output

    request_text = "\n".join(
        part
        for part in [
            issue_query_text(issue),
            user_instructions or "",
        ]
        if part
    )
    if (
        not SIMPLE_TEST_FILE_REQUEST_RE.search(
            request_text
        )
        or TEST_FRAMEWORK_REQUEST_RE.search(
            request_text
        )
    ):
        return output

    normalized = output.model_copy(
        deep=True
    )
    normalized.summary = (
        "Create a minimal plain-text test.txt file at the repository root."
    )
    normalized.problem_analysis = (
        "The issue explicitly requests a new test file but does not require "
        "a test framework, executable test suite, dependency, or CI change. "
        "The smallest safe interpretation is a plain repository-root test.txt."
    )
    normalized.likely_root_cause = None
    normalized.confidence = max(
        normalized.confidence,
        0.75,
    )
    normalized.files_to_modify = [
        PlannedFile(
            path="test.txt",
            change_type="create",
            reason=(
                "The issue explicitly requests a new test file; use a minimal "
                "plain-text artifact without adding dependencies."
            ),
            references=[],
        )
    ]
    normalized.implementation_steps = [
        ImplementationStep(
            order=1,
            description=(
                "Create test.txt at the repository root with minimal "
                "placeholder content describing that it is the requested "
                "test file. Do not add a framework, dependencies, or CI."
            ),
            files=[
                "test.txt"
            ],
        )
    ]
    normalized.tests = [
        TestPlanItem(
            description=(
                "Verify test.txt is created at the repository root and "
                "contains the requested placeholder content."
            ),
            test_type="file",
        )
    ]
    normalized.risks = [
        (
            "The issue does not specify file content, so the change is "
            "intentionally limited to a plain-text placeholder."
        )
    ]
    normalized.assumptions = [
        *normalized.assumptions,
        (
            "The phrase 'test file' means a plain test.txt artifact, not a "
            "framework-specific executable test."
        ),
    ]
    normalized.needs_more_context = False
    normalized.missing_context = []
    return normalized


def planner_failure_message(
    error: Exception,
) -> str:
    if isinstance(
        error,
        AgentConfigurationError,
    ):
        return str(error)
    if isinstance(
        error,
        OpenAIError,
    ):
        return (
            "OpenAI planning request failed. Verify OPENAI_API_KEY "
            f"and access to the {settings.planner_model} model."
        )
    return (
        "Planner failed before producing a valid plan "
        f"({error.__class__.__name__})."
    )


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
        task = None

        if task_id is not None:
            task = await task_service.require_task(
                task_id=task_id,
                db=db,
            )
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
                issue_summary=(
                    task.issue_summary
                    if task is not None
                    else None
                ),
                user_instructions=(
                    task.user_instructions
                    if task is not None
                    else None
                ),
            )
        except PlannerInputError as exc:
            log_task_failure(
                "planner.input_failed",
                exc,
                task_id=(
                    str(task_id)
                    if task_id is not None
                    else None
                ),
                workspace_id=workspace_id,
                repository=f"{owner}/{repo}",
                issue_number=issue.get("number"),
            )
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
            normalized_output = apply_safe_planning_defaults(
                output=output,
                issue=issue,
                user_instructions=(
                    task.user_instructions
                    if task is not None
                    else None
                ),
            )
            if normalized_output is not output:
                log_task_event(
                    "planner.safe_default_applied",
                    task_id=(
                        str(task_id)
                        if task_id is not None
                        else None
                    ),
                    workspace_id=workspace_id,
                    repository=f"{owner}/{repo}",
                    issue_number=issue.get(
                        "number"
                    ),
                    path="test.txt",
                    default_type="plain_test_file",
                )
                output = normalized_output
        except Exception as exc:
            failure_message = planner_failure_message(
                exc
            )
            log_task_failure(
                "planner.execution_failed",
                exc,
                task_id=(
                    str(task_id)
                    if task_id is not None
                    else None
                ),
                workspace_id=workspace_id,
                repository=f"{owner}/{repo}",
                issue_number=issue.get("number"),
                model=self.planner_runner.model,
                public_message=failure_message,
            )
            if task_id is not None:
                if agent_run is not None:
                    await task_service.complete_agent_run(
                        agent_run_id=agent_run.id,
                        db=db,
                        status="failed",
                        error_type=exc.__class__.__name__,
                        error_message=failure_message,
                    )
                await task_service.set_failure(
                    task_id=task_id,
                    db=db,
                    failure_category=PLANNER_ERROR,
                    error=exc,
                    public_message=failure_message,
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
            log_task_failure(
                "planner.validation_failed",
                exc,
                task_id=(
                    str(task_id)
                    if task_id is not None
                    else None
                ),
                workspace_id=workspace_id,
                repository=f"{owner}/{repo}",
                issue_number=issue.get("number"),
                model=self.planner_runner.model,
            )
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
                await task_service.transition_task(
                    task_id=task_id,
                    new_status=PLAN_REVISION_REQUIRED,
                    db=db,
                    failure_category=PLANNER_VALIDATION_ERROR,
                    last_error=str(exc),
                    last_error_type=exc.__class__.__name__,
                    event_type="planner.plan_revision_required",
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
            if output.needs_more_context:
                await task_service.transition_task(
                    task_id=task_id,
                    new_status=PLAN_REVISION_REQUIRED,
                    db=db,
                    event_type="planner.more_context_required",
                    active_plan_id=plan.id,
                    failure_category=PLAN_REVISION_REQUIRED,
                    last_error=(
                        "Planner needs more context: "
                        + "; ".join(
                            output.missing_context
                        )
                    ),
                    last_error_type="PlannerNeedsMoreContext",
                    metadata={
                        "plan_id": str(plan.id),
                        "missing_context": (
                            output.missing_context
                        ),
                    },
                )
            else:
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
            if (
                not output.needs_more_context
                and task is not None
                and task.autonomy_mode == "standard"
            ):
                plan = await self.approve_plan(
                    plan_id=plan.id,
                    db=db,
                )
                await task_service.record_event(
                    task_id=task_id,
                    event_type="plan.auto_approved",
                    db=db,
                    metadata={
                        "plan_id": str(plan.id),
                        "autonomy_mode": "standard",
                    },
                    commit=True,
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
        if (
            plan.plan_json or {}
        ).get(
            "needs_more_context"
        ):
            raise PlanStateError(
                "Plan cannot be approved until its missing context is resolved"
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
