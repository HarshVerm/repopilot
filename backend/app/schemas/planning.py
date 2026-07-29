from typing import Any

from pydantic import (
    BaseModel,
    Field,
)


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


class PlannedFile(BaseModel):
    path: str = Field(
        min_length=1,
        max_length=500,
    )
    reason: str = Field(
        min_length=1,
        max_length=1000,
    )
    references: list[SourceReference]


class ImplementationStep(BaseModel):
    order: int = Field(
        ge=1,
    )
    description: str = Field(
        min_length=1,
        max_length=2000,
    )
    files: list[str]


class TestPlanItem(BaseModel):
    description: str = Field(
        min_length=1,
        max_length=2000,
    )
    test_type: str = Field(
        min_length=1,
        max_length=100,
    )


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


class RejectPlanRequest(BaseModel):
    reason: str | None = Field(
        default=None,
        max_length=2000,
    )


class PlannerExecutionMetadata(BaseModel):
    model: str | None = None
    latency_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    trace_include_sensitive_data: bool


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


class PlanStatusResponse(BaseModel):
    plan_id: str
    status: str
    rejection_reason: str | None = None


class PlanningErrorResponse(BaseModel):
    detail: str
    code: str
    metadata: dict[str, Any] | None = None
