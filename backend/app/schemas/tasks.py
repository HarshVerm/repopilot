# Module purpose: Define validated tasks API payload schemas.

from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)
from uuid import UUID


# Purpose: Validate and represent create task request data.
class CreateTaskRequest(BaseModel):
    repository_id: UUID | None = None
    owner: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9_.-]+$",
    )
    repo: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9_.-]+$",
    )
    issue_number: int = Field(
        ge=1,
    )
    user_instructions: str | None = Field(
        default=None,
        max_length=10_000,
    )

    # Purpose: Validate repository reference for the task lifecycle workflow.
    @model_validator(mode="after")
    def validate_repository_reference(
        self,
    ) -> "CreateTaskRequest":
        native = self.repository_id is not None
        legacy = self.owner is not None and self.repo is not None
        if native == legacy:
            raise ValueError(
                "Provide repository_id or legacy owner/repo, but not both"
            )
        return self


# Purpose: Validate optional input supplied when restarting a stopped task.
class RestartTaskRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    clarification: str | None = Field(
        default=None,
        min_length=1,
        max_length=10_000,
    )


# Purpose: Validate and represent task response data.
class TaskResponse(BaseModel):
    task_id: str
    repository: dict[str, str]
    repository_id: str | None = None
    installation_id: str | None = None
    issue_number: int
    issue: dict[str, Any] | None = None
    issue_summary: str | None = None
    user_instructions: str | None = None
    autonomy_mode: str = "strict"
    base_branch: str | None = None
    base_commit_sha: str | None = None
    workspace_id: str | None
    status: str
    current_step: int
    started_at: str | None
    completed_at: str | None
    cancelled_at: str | None = None
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


# Purpose: Validate and represent task list response data.
class TaskListResponse(BaseModel):
    tasks: list[TaskResponse]


# Purpose: Validate and represent task timeline event response data.
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


# Purpose: Validate and represent task timeline response data.
class TaskTimelineResponse(BaseModel):
    task_id: str
    events: list[TaskTimelineEventResponse]


# Purpose: Validate and represent task metrics response data.
class TaskMetricsResponse(BaseModel):
    task_id: str
    metrics: dict[str, Any]


# Purpose: Validate and represent cancel task response data.
class CancelTaskResponse(BaseModel):
    task_id: str
    status: str
    cancel_requested: bool


# Purpose: Validate and represent reconcile task response data.
class ReconcileTaskResponse(BaseModel):
    task: TaskResponse
