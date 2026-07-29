from pydantic import (
    BaseModel,
    Field,
    ConfigDict,
)


class DebuggerOutput(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    diagnosis: str = Field(
        min_length=1,
        max_length=4000,
    )
    failure_category: str = Field(
        min_length=1,
        max_length=100,
    )
    likely_root_cause: str = Field(
        min_length=1,
        max_length=4000,
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
    )
    files_to_modify: list[str] = Field(
        default_factory=list
    )
    repair_steps: list[str] = Field(
        default_factory=list
    )
    retry_recommended: bool = True
    needs_plan_revision: bool = False
    revision_reason: str | None = Field(
        default=None,
        max_length=2000,
    )


class DebugAttemptHistoryItem(BaseModel):
    debug_attempt_id: str
    attempt: int
    failure_category: str
    status: str
    parent_change_set_id: str
    new_change_set_id: str | None
    failed_execution_run_id: str
    retry_execution_run_id: str | None
    diagnosis: str | None
    stop_reason: str | None = None


class DebugRunResponse(BaseModel):
    status: str
    reason: str | None = None
    attempts: int
    final_change_set_id: str | None = None
    final_execution_run_id: str | None = None
    history: list[DebugAttemptHistoryItem]


class DebugAttemptResponse(DebugAttemptHistoryItem):
    workspace_id: str
    plan_id: str
    likely_root_cause: str | None = None
    confidence: float | None = None
    diff_hash: str | None = None
    failure_fingerprint: str | None = None
