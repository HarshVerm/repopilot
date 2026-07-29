from typing import Any

from pydantic import (
    BaseModel,
    Field,
)


class CreateTaskRequest(BaseModel):
    owner: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9_.-]+$",
    )
    repo: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9_.-]+$",
    )
    issue_number: int = Field(
        ge=1,
    )


class TaskResponse(BaseModel):
    task_id: str
    repository: dict[str, str]
    issue_number: int
    workspace_id: str | None
    status: str
    current_step: int
    started_at: str | None
    completed_at: str | None
    last_error: str | None
    last_error_type: str | None
    failure_category: str | None
    retryable: bool | None
    cancel_requested: bool
    version: int
    active_plan_id: str | None
    active_change_set_id: str | None
    active_execution_run_id: str | None
    active_review_id: str | None
    publication_id: str | None
    last_event_at: str | None
    created_at: str | None
    updated_at: str | None
    metrics: dict[str, Any] | None = None


class TaskListResponse(BaseModel):
    tasks: list[TaskResponse]


class TaskTimelineEventResponse(BaseModel):
    event_id: str
    task_id: str
    event_type: str
    step: int | None
    status: str | None
    message: str | None
    metadata: dict[str, Any]
    request_id: str | None
    correlation_id: str | None
    agent_run_id: str | None
    created_at: str | None


class TaskTimelineResponse(BaseModel):
    task_id: str
    events: list[TaskTimelineEventResponse]


class TaskMetricsResponse(BaseModel):
    task_id: str
    metrics: dict[str, Any]


class CancelTaskResponse(BaseModel):
    task_id: str
    status: str
    cancel_requested: bool


class ReconcileTaskResponse(BaseModel):
    task: TaskResponse
