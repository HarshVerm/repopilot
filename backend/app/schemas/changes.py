from pydantic import (
    BaseModel,
    Field,
)


class FileChange(BaseModel):
    path: str = Field(
        min_length=1,
        max_length=500,
    )
    change_type: str = Field(
        min_length=1,
        max_length=50,
    )
    summary: str = Field(
        min_length=1,
        max_length=1000,
    )


class CoderOutput(BaseModel):
    summary: str = Field(
        min_length=1,
        max_length=2000,
    )
    files_changed: list[FileChange] = Field(
        default_factory=list
    )
    implementation_notes: list[str] = Field(
        default_factory=list
    )
    assumptions: list[str] = Field(
        default_factory=list
    )
    needs_plan_revision: bool = False
    revision_reason: str | None = Field(
        default=None,
        max_length=2000,
    )


class ChangeSetFileResponse(BaseModel):
    path: str
    before_sha256: str
    after_sha256: str
    lines_added: int
    lines_deleted: int


class ImplementPlanResponse(BaseModel):
    change_set_id: str
    plan_id: str
    workspace_id: str
    status: str
    base_commit_sha: str
    summary: str | None
    files_changed: list[ChangeSetFileResponse]
    lines_added: int
    lines_deleted: int
    tests_run: bool
    revision_reason: str | None = None


class ChangeSetDiffResponse(BaseModel):
    change_set_id: str
    plan_id: str
    base_commit_sha: str
    files_changed: list[ChangeSetFileResponse]
    lines_added: int
    lines_deleted: int
    diff: str | None
    tests_run: bool
