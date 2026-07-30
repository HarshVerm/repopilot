# Module purpose: Define validated planning API payload schemas.

from typing import Any, Literal

from pydantic import (
    BaseModel,
    Field,
)


# Purpose: Validate and represent source reference data.
class SourceReference(BaseModel):
    file_path: str = Field(
        min_length=1,
        max_length=500,
    )
    start_line: int | None = Field(
        default=None,
        ge=1,
    )
    end_line: int | None = Field(
        default=None,
        ge=1,
    )


# Purpose: Validate and represent planned file data.
class PlannedFile(BaseModel):
    path: str = Field(
        min_length=1,
        max_length=500,
    )
    change_type: Literal[
        "modify",
        "create",
    ] = "modify"
    reason: str = Field(
        min_length=1,
        max_length=1000,
    )
    references: list[SourceReference]


# Purpose: Validate and represent implementation step data.
class ImplementationStep(BaseModel):
    order: int = Field(
        ge=1,
    )
    description: str = Field(
        min_length=1,
        max_length=2000,
    )
    files: list[str]


# Purpose: Validate and represent test plan item data.
class TestPlanItem(BaseModel):
    description: str = Field(
        min_length=1,
        max_length=2000,
    )
    test_type: str = Field(
        min_length=1,
        max_length=100,
    )


# Purpose: Validate and represent planner output data.
class PlannerOutput(BaseModel):
    summary: str = Field(
        min_length=1,
        max_length=2000,
    )
    problem_analysis: str = Field(
        min_length=1,
        max_length=5000,
    )
    likely_root_cause: str | None = Field(
        default=...
    )
    confidence: float = Field(
        ge=0,
        le=1,
    )
    files_to_inspect: list[PlannedFile]
    files_to_modify: list[PlannedFile]
    implementation_steps: list[ImplementationStep]
    tests: list[TestPlanItem]
    risks: list[str]
    assumptions: list[str]
    needs_more_context: bool
    missing_context: list[str]


# Purpose: Validate and represent create plan request data.
class CreatePlanRequest(BaseModel):
    owner: str = Field(
        min_length=1,
        max_length=100,
    )
    repo: str = Field(
        min_length=1,
        max_length=100,
    )
    issue_number: int = Field(
        ge=1,
    )


# Purpose: Validate and represent reject plan request data.
class RejectPlanRequest(BaseModel):
    reason: str | None = Field(
        default=None,
        max_length=2000,
    )


# Purpose: Validate and represent planner execution metadata data.
class PlannerExecutionMetadata(BaseModel):
    model: str | None = None
    latency_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    trace_include_sensitive_data: bool


# Purpose: Validate and represent plan response data.
class PlanResponse(BaseModel):
    plan_id: str
    status: str
    workspace_id: str
    owner: str
    repo: str
    issue_number: int
    plan: PlannerOutput
    rejection_reason: str | None = None
    metadata: PlannerExecutionMetadata


# Purpose: Validate and represent plan status response data.
class PlanStatusResponse(BaseModel):
    plan_id: str
    status: str
    rejection_reason: str | None = None


# Purpose: Validate and represent planning error response data.
class PlanningErrorResponse(BaseModel):
    detail: str
    code: str
    metadata: dict[str, Any] | None = None
