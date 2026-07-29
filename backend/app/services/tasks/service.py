import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent_run import AgentRun
from app.db.models.change_set import ChangeSet
from app.db.models.debug_attempt import DebugAttempt
from app.db.models.execution_plan import ExecutionPlan
from app.db.models.execution_run import ExecutionRun
from app.db.models.final_review import FinalReview
from app.db.models.publication import Publication
from app.db.models.task import RepoPilotTask
from app.db.models.task_event import TaskEvent
from app.observability.correlation import (
    get_correlation_id,
    get_request_id,
)
from app.observability.logging import (
    log_task_event,
)
from app.observability.redaction import (
    bounded_metadata,
    redact_string,
)
from app.services.tasks.failures import (
    normalize_failure_category,
    retryable_for_category,
)
from app.services.hardening.validation import (
    validate_task_event_metadata,
)
from app.services.tasks.state_machine import (
    CANCELLABLE_STATES,
    CANCELLED,
    COMPLETED,
    CREATED,
    FAILED,
    REPOSITORY_PREPARING,
    REPOSITORY_READY,
    TERMINAL_STATES,
    TaskConcurrencyError,
    TaskStateMachine,
    TaskTransitionError,
)


SLUG_RE = re.compile(
    r"^[A-Za-z0-9_.-]{1,100}$"
)


class TaskValidationError(ValueError):
    pass


class TaskNotFoundError(KeyError):
    pass


class TaskService:
    def __init__(
        self,
        *,
        state_machine: TaskStateMachine | None = None,
    ) -> None:
        self.state_machine = (
            state_machine or TaskStateMachine()
        )

    async def create_task(
        self,
        *,
        owner: str,
        repo: str,
        issue_number: int,
        db: AsyncSession,
        reuse_active: bool = True,
    ) -> RepoPilotTask:
        validate_task_identity(
            owner=owner,
            repo=repo,
            issue_number=issue_number,
        )
        existing = None

        if reuse_active:
            existing = await self.find_active_task(
                owner=owner,
                repo=repo,
                issue_number=issue_number,
                db=db,
            )

        if existing is not None:
            await self.record_event(
                task_id=existing.id,
                event_type="task.duplicate_returned",
                db=db,
                metadata={
                    "repository": f"{owner}/{repo}",
                    "issue_number": issue_number,
                },
                commit=True,
            )
            return existing

        now = datetime.now(
            UTC
        )
        task = RepoPilotTask(
            repository_owner=owner,
            repository_name=repo,
            issue_number=issue_number,
            status=CREATED,
            current_step=self.state_machine.step_for_status(
                CREATED
            ),
            started_at=now,
            last_event_at=now,
        )
        db.add(task)
        await db.flush()
        self.add_event(
            task=task,
            event_type="task.created",
            metadata={
                "repository": f"{owner}/{repo}",
                "issue_number": issue_number,
            },
            db=db,
        )
        await db.commit()
        await db.refresh(task)
        return task

    async def list_tasks(
        self,
        *,
        db: AsyncSession,
        status: str | None = None,
        owner: str | None = None,
        repo: str | None = None,
        issue_number: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[RepoPilotTask]:
        stmt = select(RepoPilotTask)

        if status:
            stmt = stmt.where(
                RepoPilotTask.status == status
            )
        if owner:
            stmt = stmt.where(
                RepoPilotTask.repository_owner
                == owner
            )
        if repo:
            stmt = stmt.where(
                RepoPilotTask.repository_name == repo
            )
        if issue_number:
            stmt = stmt.where(
                RepoPilotTask.issue_number
                == issue_number
            )

        stmt = (
            stmt.order_by(
                RepoPilotTask.created_at.desc()
            )
            .limit(limit)
            .offset(offset)
        )
        result = await db.scalars(stmt)
        return list(result)

    async def get_task(
        self,
        *,
        task_id: uuid.UUID,
        db: AsyncSession,
    ) -> RepoPilotTask | None:
        return await db.get(
            RepoPilotTask,
            task_id,
        )

    async def require_task(
        self,
        *,
        task_id: uuid.UUID,
        db: AsyncSession,
    ) -> RepoPilotTask:
        task = await self.get_task(
            task_id=task_id,
            db=db,
        )

        if task is None:
            raise TaskNotFoundError(
                "Task not found"
            )

        return task

    async def find_active_task(
        self,
        *,
        owner: str,
        repo: str,
        issue_number: int,
        db: AsyncSession,
    ) -> RepoPilotTask | None:
        result = await db.scalars(
            select(RepoPilotTask)
            .where(
                RepoPilotTask.repository_owner
                == owner,
                RepoPilotTask.repository_name == repo,
                RepoPilotTask.issue_number
                == issue_number,
                RepoPilotTask.status.not_in(
                    list(TERMINAL_STATES)
                ),
            )
            .order_by(
                RepoPilotTask.created_at.desc()
            )
            .limit(1)
        )
        return result.first()

    async def find_task_by_workspace(
        self,
        *,
        workspace_id: str,
        db: AsyncSession,
    ) -> RepoPilotTask | None:
        result = await db.scalars(
            select(RepoPilotTask)
            .where(
                RepoPilotTask.workspace_id
                == workspace_id,
                RepoPilotTask.status.not_in(
                    list(TERMINAL_STATES)
                ),
            )
            .order_by(
                RepoPilotTask.created_at.desc()
            )
            .limit(1)
        )
        return result.first()

    async def task_for_plan(
        self,
        *,
        plan: ExecutionPlan,
        db: AsyncSession,
    ) -> RepoPilotTask | None:
        if plan.task_id:
            return await self.get_task(
                task_id=plan.task_id,
                db=db,
            )

        return await self.find_active_task(
            owner=plan.repository_owner,
            repo=plan.repository_name,
            issue_number=plan.issue_number,
            db=db,
        )

    async def attach_workspace(
        self,
        *,
        task_id: uuid.UUID,
        workspace_id: str,
        db: AsyncSession,
    ) -> RepoPilotTask:
        task = await self.require_task(
            task_id=task_id,
            db=db,
        )

        if (
            task.workspace_id is not None
            and task.workspace_id != workspace_id
        ):
            raise TaskValidationError(
                "Task is already attached to a different workspace"
            )

        if task.workspace_id is None:
            task.workspace_id = workspace_id

        if task.status == CREATED:
            await self.transition_task(
                task_id=task_id,
                new_status=REPOSITORY_PREPARING,
                db=db,
                event_type="repository.clone.started",
                metadata={
                    "workspace_id": workspace_id
                },
            )
            task = await self.require_task(
                task_id=task_id,
                db=db,
            )

        if task.status == REPOSITORY_PREPARING:
            await self.transition_task(
                task_id=task_id,
                new_status=REPOSITORY_READY,
                db=db,
                event_type="repository.clone.completed",
                metadata={
                    "workspace_id": workspace_id
                },
            )
            task = await self.require_task(
                task_id=task_id,
                db=db,
            )
        else:
            await self.record_event(
                task_id=task_id,
                event_type="repository.ready",
                metadata={
                    "workspace_id": workspace_id
                },
                db=db,
                commit=True,
            )

        return task

    async def transition_task(
        self,
        *,
        task_id: uuid.UUID,
        new_status: str,
        db: AsyncSession,
        expected_version: int | None = None,
        event_type: str | None = None,
        metadata: dict[str, Any] | None = None,
        message: str | None = None,
        failure_category: str | None = None,
        last_error: str | None = None,
        last_error_type: str | None = None,
        active_plan_id: uuid.UUID | None = None,
        active_change_set_id: uuid.UUID | None = None,
        active_execution_run_id: uuid.UUID | None = None,
        active_review_id: uuid.UUID | None = None,
        publication_id: uuid.UUID | None = None,
        allow_reconcile: bool = False,
    ) -> RepoPilotTask:
        task = await self.require_task(
            task_id=task_id,
            db=db,
        )
        await db.refresh(task)

        if (
            expected_version is not None
            and task.version != expected_version
        ):
            raise TaskConcurrencyError(
                "Task version changed"
            )

        if allow_reconcile:
            self.state_machine.validate_reconciliation(
                current_status=task.status,
                new_status=new_status,
            )
        else:
            self.state_machine.validate_transition(
                current_status=task.status,
                new_status=new_status,
            )

        now = datetime.now(
            UTC
        )
        changed_status = (
            task.status != new_status
        )
        task.status = new_status
        task.current_step = (
            self.state_machine.step_for_status(
                new_status
            )
        )
        task.version += 1
        task.last_event_at = now

        if new_status in TERMINAL_STATES:
            task.completed_at = (
                task.completed_at or now
            )

        if failure_category is not None:
            normalized = normalize_failure_category(
                failure_category
            )
            task.failure_category = normalized
            task.retryable = retryable_for_category(
                normalized
            )

        if last_error is not None:
            task.last_error = redact_string(
                last_error
            )
        if last_error_type is not None:
            task.last_error_type = last_error_type

        if active_plan_id is not None:
            task.active_plan_id = active_plan_id
        if active_change_set_id is not None:
            task.active_change_set_id = (
                active_change_set_id
            )
        if active_execution_run_id is not None:
            task.active_execution_run_id = (
                active_execution_run_id
            )
        if active_review_id is not None:
            task.active_review_id = active_review_id
        if publication_id is not None:
            task.publication_id = publication_id

        self.add_event(
            task=task,
            event_type=event_type
            or (
                "task.status_changed"
                if changed_status
                else "task.event"
            ),
            metadata=metadata,
            message=message,
            db=db,
        )
        await db.commit()
        await db.refresh(task)
        return task

    async def set_failure(
        self,
        *,
        task_id: uuid.UUID,
        db: AsyncSession,
        failure_category: str,
        error: Exception | str,
        event_type: str = "task.failed",
        metadata: dict[str, Any] | None = None,
    ) -> RepoPilotTask:
        message = (
            str(error)
            if isinstance(error, str)
            else error.__class__.__name__
        )
        error_type = (
            None
            if isinstance(error, str)
            else error.__class__.__name__
        )
        return await self.transition_task(
            task_id=task_id,
            new_status=FAILED,
            db=db,
            event_type=event_type,
            failure_category=failure_category,
            last_error=message,
            last_error_type=error_type,
            metadata=metadata,
            message=message,
        )

    async def request_cancel(
        self,
        *,
        task_id: uuid.UUID,
        db: AsyncSession,
    ) -> RepoPilotTask:
        task = await self.require_task(
            task_id=task_id,
            db=db,
        )

        if task.status not in CANCELLABLE_STATES:
            raise TaskTransitionError(
                f"Task cannot be cancelled from {task.status}"
            )

        task.cancel_requested = True
        await db.commit()
        return await self.transition_task(
            task_id=task_id,
            new_status=CANCELLED,
            db=db,
            event_type="task.cancelled",
            failure_category="cancelled",
        )

    async def start_agent_run(
        self,
        *,
        task_id: uuid.UUID,
        agent_type: str,
        model: str,
        db: AsyncSession,
        plan_id: uuid.UUID | None = None,
        change_set_id: uuid.UUID | None = None,
        debug_attempt_id: uuid.UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentRun:
        agent_run = AgentRun(
            task_id=task_id,
            agent_type=agent_type,
            model=model,
            status="started",
            started_at=datetime.now(
                UTC
            ),
            plan_id=plan_id,
            change_set_id=change_set_id,
            debug_attempt_id=debug_attempt_id,
            request_id=get_request_id(),
            correlation_id=get_correlation_id(),
        )
        db.add(agent_run)
        await db.flush()
        await self.record_event(
            task_id=task_id,
            event_type=f"{agent_type}.started",
            agent_run_id=agent_run.id,
            metadata=metadata,
            db=db,
            commit=False,
        )
        await db.commit()
        await db.refresh(agent_run)
        return agent_run

    async def complete_agent_run(
        self,
        *,
        agent_run_id: uuid.UUID,
        db: AsyncSession,
        status: str,
        latency_ms: float | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        total_tokens: int | None = None,
        tool_calls_count: int | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
        plan_id: uuid.UUID | None = None,
        change_set_id: uuid.UUID | None = None,
        debug_attempt_id: uuid.UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentRun:
        agent_run = await db.get(
            AgentRun,
            agent_run_id,
        )

        if agent_run is None:
            raise TaskNotFoundError(
                "AgentRun not found"
            )

        agent_run.status = status
        agent_run.completed_at = datetime.now(
            UTC
        )
        agent_run.latency_ms = latency_ms
        agent_run.input_tokens = input_tokens
        agent_run.output_tokens = output_tokens
        agent_run.total_tokens = total_tokens
        if tool_calls_count is not None:
            agent_run.tool_calls_count = (
                tool_calls_count
            )
        agent_run.error_type = error_type
        agent_run.error_message = (
            redact_string(error_message)
            if error_message
            else None
        )

        if plan_id is not None:
            agent_run.plan_id = plan_id
        if change_set_id is not None:
            agent_run.change_set_id = change_set_id
        if debug_attempt_id is not None:
            agent_run.debug_attempt_id = (
                debug_attempt_id
            )

        await self.record_event(
            task_id=agent_run.task_id,
            event_type=(
                f"{agent_run.agent_type}.completed"
                if status == "completed"
                else f"{agent_run.agent_type}.failed"
            ),
            agent_run_id=agent_run.id,
            metadata=metadata,
            db=db,
            commit=False,
        )
        await db.commit()
        await db.refresh(agent_run)
        return agent_run

    async def record_event(
        self,
        *,
        task_id: uuid.UUID,
        event_type: str,
        db: AsyncSession,
        status: str | None = None,
        step: int | None = None,
        metadata: dict[str, Any] | None = None,
        message: str | None = None,
        agent_run_id: uuid.UUID | None = None,
        commit: bool = True,
    ) -> TaskEvent:
        task = await self.require_task(
            task_id=task_id,
            db=db,
        )
        event = self.add_event(
            task=task,
            event_type=event_type,
            metadata=metadata,
            message=message,
            status=status,
            step=step,
            agent_run_id=agent_run_id,
            db=db,
        )

        if commit:
            await db.commit()
            await db.refresh(event)

        return event

    def add_event(
        self,
        *,
        task: RepoPilotTask,
        event_type: str,
        metadata: dict[str, Any] | None = None,
        message: str | None = None,
        status: str | None = None,
        step: int | None = None,
        agent_run_id: uuid.UUID | None = None,
        db: AsyncSession | None = None,
    ) -> TaskEvent:
        now = datetime.now(
            UTC
        )
        event = TaskEvent(
            task_id=task.id,
            event_type=event_type,
            status=status or task.status,
            step=step or task.current_step,
            metadata_json=bounded_metadata(
                validate_task_event_metadata(
                    metadata
                )
            ),
            message=(
                redact_string(message)
                if message
                else None
            ),
            request_id=get_request_id(),
            correlation_id=get_correlation_id(),
            agent_run_id=agent_run_id,
        )
        task.last_event_at = now
        log_task_event(
            event_type,
            task_id=str(task.id),
            status=event.status,
            step=event.step,
            metadata=metadata or {},
            message=message,
        )
        task.last_event_at = now
        if db is not None:
            db.add(event)

        return event


def validate_task_identity(
    *,
    owner: str,
    repo: str,
    issue_number: int,
) -> None:
    if not SLUG_RE.match(owner):
        raise TaskValidationError(
            "Invalid repository owner"
        )
    if not SLUG_RE.match(repo):
        raise TaskValidationError(
            "Invalid repository name"
        )
    if issue_number < 1:
        raise TaskValidationError(
            "Issue number must be positive"
        )


def isoformat(
    value,
) -> str | None:
    if value is None:
        return None

    return value.isoformat()


def serialize_task(
    task: RepoPilotTask,
    *,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "task_id": str(task.id),
        "repository": {
            "owner": task.repository_owner,
            "repo": task.repository_name,
        },
        "issue_number": task.issue_number,
        "workspace_id": task.workspace_id,
        "status": task.status,
        "current_step": task.current_step,
        "started_at": isoformat(task.started_at),
        "completed_at": isoformat(
            task.completed_at
        ),
        "last_error": task.last_error,
        "last_error_type": task.last_error_type,
        "failure_category": task.failure_category,
        "retryable": task.retryable,
        "cancel_requested": task.cancel_requested,
        "version": task.version,
        "active_plan_id": (
            str(task.active_plan_id)
            if task.active_plan_id
            else None
        ),
        "active_change_set_id": (
            str(task.active_change_set_id)
            if task.active_change_set_id
            else None
        ),
        "active_execution_run_id": (
            str(task.active_execution_run_id)
            if task.active_execution_run_id
            else None
        ),
        "active_review_id": (
            str(task.active_review_id)
            if task.active_review_id
            else None
        ),
        "publication_id": (
            str(task.publication_id)
            if task.publication_id
            else None
        ),
        "last_event_at": isoformat(
            task.last_event_at
        ),
        "created_at": isoformat(task.created_at),
        "updated_at": isoformat(task.updated_at),
        "metrics": metrics,
    }


def serialize_timeline_event(
    event: TaskEvent,
) -> dict[str, Any]:
    return {
        "event_id": str(event.id),
        "task_id": str(event.task_id),
        "event_type": event.event_type,
        "step": event.step,
        "status": event.status,
        "message": event.message,
        "metadata": event.metadata_json or {},
        "request_id": event.request_id,
        "correlation_id": event.correlation_id,
        "agent_run_id": (
            str(event.agent_run_id)
            if event.agent_run_id
            else None
        ),
        "created_at": isoformat(event.created_at),
    }


def serialize_agent_run(
    agent_run: AgentRun,
) -> dict[str, Any]:
    return {
        "agent_run_id": str(agent_run.id),
        "task_id": str(agent_run.task_id),
        "agent_type": agent_run.agent_type,
        "model": agent_run.model,
        "status": agent_run.status,
        "started_at": isoformat(
            agent_run.started_at
        ),
        "completed_at": isoformat(
            agent_run.completed_at
        ),
        "latency_ms": agent_run.latency_ms,
        "input_tokens": agent_run.input_tokens,
        "output_tokens": agent_run.output_tokens,
        "total_tokens": agent_run.total_tokens,
        "tool_calls_count": (
            agent_run.tool_calls_count
        ),
        "error_type": agent_run.error_type,
        "error_message": agent_run.error_message,
        "plan_id": (
            str(agent_run.plan_id)
            if agent_run.plan_id
            else None
        ),
        "change_set_id": (
            str(agent_run.change_set_id)
            if agent_run.change_set_id
            else None
        ),
        "debug_attempt_id": (
            str(agent_run.debug_attempt_id)
            if agent_run.debug_attempt_id
            else None
        ),
    }
