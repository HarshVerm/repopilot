# Module purpose: Implement service behavior for the task lifecycle domain.

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
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
    log_task_failure,
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


# Purpose: Signal task validation failures.
class TaskValidationError(ValueError):
    pass


# Purpose: Signal task not found failures.
class TaskNotFoundError(KeyError):
    pass


# Purpose: Coordinate task operations.
class TaskService:
    # Purpose: Initialize task service state and dependencies.
    def __init__(
        self,
        *,
        state_machine: TaskStateMachine | None = None,
    ) -> None:
        self.state_machine = (
            state_machine or TaskStateMachine()
        )

    # Purpose: Create task for the task lifecycle workflow.
    async def create_task(
        self,
        *,
        owner: str,
        repo: str,
        issue_number: int,
        db: AsyncSession,
        reuse_active: bool = True,
        user_id: uuid.UUID | None = None,
        installation_id: uuid.UUID | None = None,
        repository_id: uuid.UUID | None = None,
        issue_snapshot: dict[str, Any] | None = None,
        issue_summary: str | None = None,
        user_instructions: str | None = None,
        base_branch: str | None = None,
        autonomy_mode: str = "strict",
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
                user_id=user_id,
                repository_id=repository_id,
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
            user_id=user_id,
            installation_id=installation_id,
            repository_id=repository_id,
            repository_owner=owner,
            repository_name=repo,
            issue_number=issue_number,
            status=CREATED,
            current_step=self.state_machine.step_for_status(
                CREATED
            ),
            started_at=now,
            last_event_at=now,
            github_issue_id=(
                int(issue_snapshot["id"])
                if issue_snapshot
                and issue_snapshot.get("id") is not None
                else None
            ),
            issue_title=(
                issue_snapshot.get("title")
                if issue_snapshot
                else None
            ),
            issue_body_snapshot=(
                issue_snapshot.get("body")
                if issue_snapshot
                else None
            ),
            issue_url=(
                issue_snapshot.get("html_url")
                if issue_snapshot
                else None
            ),
            issue_author=(
                (issue_snapshot.get("user") or {}).get("login")
                if issue_snapshot
                else None
            ),
            issue_labels=(
                [
                    (
                        label.get("name")
                        if isinstance(label, dict)
                        else str(label)
                    )
                    for label in issue_snapshot.get("labels", [])
                ]
                if issue_snapshot
                else []
            ),
            issue_created_at=parse_github_datetime(
                issue_snapshot.get("created_at")
                if issue_snapshot
                else None
            ),
            issue_updated_at_at_creation=parse_github_datetime(
                issue_snapshot.get("updated_at")
                if issue_snapshot
                else None
            ),
            issue_summary=issue_summary,
            user_instructions=user_instructions,
            base_branch=base_branch,
            autonomy_mode=autonomy_mode,
        )
        db.add(task)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            if (
                reuse_active
                and user_id is not None
                and repository_id is not None
            ):
                concurrent = await self.find_active_task(
                    owner=owner,
                    repo=repo,
                    issue_number=issue_number,
                    db=db,
                    user_id=user_id,
                    repository_id=repository_id,
                )
                if concurrent is not None:
                    await self.record_event(
                        task_id=concurrent.id,
                        event_type="task.duplicate_returned",
                        db=db,
                        metadata={
                            "repository": f"{owner}/{repo}",
                            "issue_number": issue_number,
                            "reason": "concurrent_create",
                        },
                        commit=True,
                    )
                    return concurrent
            raise
        self.add_event(
            task=task,
            event_type="task.created",
            metadata={
                "repository": f"{owner}/{repo}",
                "issue_number": issue_number,
                "repository_id": (
                    str(repository_id)
                    if repository_id
                    else None
                ),
                "autonomy_mode": autonomy_mode,
            },
            db=db,
        )
        await db.commit()
        await db.refresh(task)
        return task

    # Purpose: List tasks for the task lifecycle workflow.
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
        user_id: uuid.UUID | None = None,
    ) -> list[RepoPilotTask]:
        stmt = select(RepoPilotTask)
        stmt = stmt.where(
            RepoPilotTask.user_id == user_id
            if user_id is not None
            else RepoPilotTask.user_id.is_(None)
        )

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

    # Purpose: Return task for the task lifecycle workflow.
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

    # Purpose: Return user task for the task lifecycle workflow.
    async def get_user_task(
        self,
        *,
        task_id: uuid.UUID,
        user_id: uuid.UUID | None,
        db: AsyncSession,
    ) -> RepoPilotTask | None:
        return await db.scalar(
            select(RepoPilotTask).where(
                RepoPilotTask.id == task_id,
                (
                    RepoPilotTask.user_id == user_id
                    if user_id is not None
                    else RepoPilotTask.user_id.is_(None)
                ),
            )
        )

    # Purpose: Require task, raising an error when unavailable.
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

    # Purpose: Find active task for the task lifecycle workflow.
    async def find_active_task(
        self,
        *,
        owner: str,
        repo: str,
        issue_number: int,
        db: AsyncSession,
        user_id: uuid.UUID | None = None,
        repository_id: uuid.UUID | None = None,
    ) -> RepoPilotTask | None:
        result = await db.scalars(
            select(RepoPilotTask)
            .where(
                RepoPilotTask.repository_owner
                == owner,
                RepoPilotTask.repository_name == repo,
                RepoPilotTask.issue_number
                == issue_number,
                (
                    RepoPilotTask.user_id == user_id
                    if user_id is not None
                    else RepoPilotTask.user_id.is_(None)
                ),
                (
                    RepoPilotTask.repository_id == repository_id
                    if repository_id is not None
                    else True
                ),
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

    # Purpose: Find task by workspace for the task lifecycle workflow.
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

    # Purpose: Handle task for plan for the task lifecycle workflow.
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

    # Purpose: Attach workspace for the task lifecycle workflow.
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
            # ``transition_task`` refreshes the task before applying the next
            # state. Flush the attachment first so that refresh cannot discard
            # the in-memory workspace ID.
            await db.flush()

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

    # Purpose: Transition task for the task lifecycle workflow.
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
        clear_failure: bool = False,
    ) -> RepoPilotTask:
        task = await self.require_task(
            task_id=task_id,
            db=db,
        )
        await db.refresh(task)
        previous_status = task.status

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
        previous_step = task.current_step
        changed_status = (
            task.status != new_status
        )
        task.status = new_status
        task.current_step = (
            previous_step
            if new_status in {
                FAILED,
                CANCELLED,
            }
            else self.state_machine.step_for_status(
                new_status
            )
        )
        task.version += 1
        task.last_event_at = now

        if clear_failure:
            task.last_error = None
            task.last_error_type = None
            task.failure_category = None
            task.retryable = None
            task.completed_at = None

        if new_status in TERMINAL_STATES:
            task.completed_at = (
                task.completed_at or now
            )
        if new_status == CANCELLED:
            task.cancelled_at = task.cancelled_at or now

        normalized_failure_category = None
        if failure_category is not None:
            normalized_failure_category = normalize_failure_category(
                failure_category
            )
            task.failure_category = normalized_failure_category
            task.retryable = retryable_for_category(
                normalized_failure_category
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

        transition_metadata = dict(
            metadata or {}
        )
        transition_metadata.setdefault(
            "previous_status",
            previous_status,
        )
        transition_metadata.setdefault(
            "new_status",
            new_status,
        )
        if clear_failure:
            transition_metadata[
                "previous_failure_cleared"
            ] = True
        if normalized_failure_category is not None:
            transition_metadata[
                "failure_category"
            ] = normalized_failure_category
        if last_error_type is not None:
            transition_metadata[
                "error_type"
            ] = last_error_type
        if last_error is not None:
            transition_metadata[
                "error_message"
            ] = task.last_error

        self.add_event(
            task=task,
            event_type=event_type
            or (
                "task.status_changed"
                if changed_status
                else "task.event"
            ),
            metadata=transition_metadata,
            message=(
                message
                or (
                    task.last_error
                    if last_error is not None
                    else None
                )
            ),
            db=db,
        )
        await db.commit()
        await db.refresh(task)
        return task

    # Purpose: Set failure for the task lifecycle workflow.
    async def set_failure(
        self,
        *,
        task_id: uuid.UUID,
        db: AsyncSession,
        failure_category: str,
        error: Exception | str,
        public_message: str | None = None,
        event_type: str = "task.failed",
        metadata: dict[str, Any] | None = None,
    ) -> RepoPilotTask:
        message = (
            public_message
            or (
                str(error)
                if isinstance(error, str)
                else error.__class__.__name__
            )
        )
        error_type = (
            None
            if isinstance(error, str)
            else error.__class__.__name__
        )
        log_fields = {
            "task_id": str(task_id),
            "failure_category": failure_category,
            "public_message": message,
            "metadata": metadata or {},
        }
        if isinstance(error, BaseException):
            log_task_failure(
                event_type,
                error,
                **log_fields,
            )
        else:
            log_task_event(
                event_type,
                **log_fields,
                error_message=error,
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

    # Purpose: Request cancel for the task lifecycle workflow.
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

    # Purpose: Start agent run for the task lifecycle workflow.
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

    # Purpose: Handle complete agent run for the task lifecycle workflow.
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

        event_metadata = {
            **(metadata or {}),
            "agent_run_id": str(agent_run.id),
            "agent_type": agent_run.agent_type,
            "model": agent_run.model,
            "latency_ms": latency_ms,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "tool_calls_count": tool_calls_count,
        }
        if error_type is not None:
            event_metadata["error_type"] = error_type
        if error_message is not None:
            event_metadata[
                "error_message"
            ] = redact_string(error_message)

        await self.record_event(
            task_id=agent_run.task_id,
            event_type=(
                f"{agent_run.agent_type}.completed"
                if status == "completed"
                else f"{agent_run.agent_type}.failed"
            ),
            agent_run_id=agent_run.id,
            metadata=event_metadata,
            message=(
                error_message
                if status != "completed"
                else None
            ),
            db=db,
            commit=False,
        )
        await db.commit()
        await db.refresh(agent_run)
        return agent_run

    # Purpose: Record event for the task lifecycle workflow.
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

    # Purpose: Add event for the task lifecycle workflow.
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


# Purpose: Validate task identity for the task lifecycle workflow.
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


# Purpose: Handle isoformat for the task lifecycle workflow.
def isoformat(
    value,
) -> str | None:
    if value is None:
        return None

    return value.isoformat()


# Purpose: Parse github datetime for the task lifecycle workflow.
def parse_github_datetime(
    value: str | datetime | None,
) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )


# Purpose: Serialize task for the task lifecycle workflow.
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
        "repository_id": (
            str(task.repository_id)
            if task.repository_id
            else None
        ),
        "installation_id": (
            str(task.installation_id)
            if task.installation_id
            else None
        ),
        "issue_number": task.issue_number,
        "issue": {
            "github_issue_id": task.github_issue_id,
            "number": task.issue_number,
            "title": task.issue_title,
            "body": task.issue_body_snapshot,
            "html_url": task.issue_url,
            "author": task.issue_author,
            "labels": task.issue_labels or [],
            "created_at": isoformat(task.issue_created_at),
            "updated_at_at_creation": isoformat(
                task.issue_updated_at_at_creation
            ),
        },
        "issue_summary": task.issue_summary,
        "user_instructions": task.user_instructions,
        "autonomy_mode": task.autonomy_mode,
        "base_branch": task.base_branch,
        "base_commit_sha": task.base_commit_sha,
        "workspace_id": task.workspace_id,
        "status": task.status,
        "current_step": task.current_step,
        "started_at": isoformat(task.started_at),
        "completed_at": isoformat(
            task.completed_at
        ),
        "cancelled_at": isoformat(task.cancelled_at),
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


# Purpose: Serialize timeline event for the task lifecycle workflow.
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


def task_issue_snapshot(task: RepoPilotTask) -> dict:
    """Return the immutable issue payload captured when the task was created."""
    return {
        "id": task.github_issue_id,
        "number": task.issue_number,
        "title": task.issue_title or "",
        "body": task.issue_body_snapshot or "",
        "html_url": task.issue_url,
        "labels": [
            {"name": label}
            for label in (task.issue_labels or [])
        ],
        "user": {"login": task.issue_author},
        "created_at": (
            task.issue_created_at.isoformat()
            if task.issue_created_at
            else None
        ),
        "updated_at": (
            task.issue_updated_at_at_creation.isoformat()
            if task.issue_updated_at_at_creation
            else None
        ),
    }


# Purpose: Serialize agent run for the task lifecycle workflow.
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
