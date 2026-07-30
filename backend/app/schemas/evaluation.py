# Module purpose: Define validated evaluation API payload schemas.

from pydantic import BaseModel, Field


# Purpose: Validate and represent evaluation run request data.
class EvaluationRunRequest(BaseModel):
    suite: str = "repopilot-eval-v1"
    task: str | None = None
    difficulty: str | None = None
    category: str | None = None
    max_tasks: int | None = Field(
        default=None,
        ge=1,
    )
    dry_run: bool = True
    live: bool = False
    mark_baseline: bool = False


# Purpose: Validate and represent evaluation run response data.
class EvaluationRunResponse(BaseModel):
    run_id: str
    report: dict
    paths: dict[str, str]


# Purpose: Validate and represent evaluation run record response data.
class EvaluationRunRecordResponse(BaseModel):
    run_id: str
    suite_name: str
    suite_version: str
    status: str
    report: dict | None = None
