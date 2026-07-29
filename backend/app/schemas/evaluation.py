from pydantic import BaseModel, Field


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


class EvaluationRunResponse(BaseModel):
    run_id: str
    report: dict
    paths: dict[str, str]


class EvaluationRunRecordResponse(BaseModel):
    run_id: str
    suite_name: str
    suite_version: str
    status: str
    report: dict | None = None
