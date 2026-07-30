# Module purpose: Define validated changes API payload schemas.

from pydantic import (
    BaseModel,
    Field,
)


# Purpose: Validate and represent file change data.
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


# Purpose: Validate and represent coder output data.
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


# Purpose: Validate and represent change set file response data.
class ChangeSetFileResponse(BaseModel):
    path: str
    before_sha256: str
    after_sha256: str
    lines_added: int
    lines_deleted: int


# Purpose: Validate and represent implement plan response data.
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


# Purpose: Validate and represent change set diff response data.
class ChangeSetDiffResponse(BaseModel):
    change_set_id: str
    plan_id: str
    base_commit_sha: str
    files_changed: list[ChangeSetFileResponse]
    lines_added: int
    lines_deleted: int
    diff: str | None
    tests_run: bool
