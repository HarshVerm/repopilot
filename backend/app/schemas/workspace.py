# Module purpose: Define validated workspace API payload schemas.

from pydantic import BaseModel, HttpUrl


# Purpose: Validate and represent clone repository request data.
class CloneRepositoryRequest(BaseModel):
    repository_url: HttpUrl


# Purpose: Validate and represent workspace response data.
class WorkspaceResponse(BaseModel):
    workspace_id: str
    repository_path: str