from pydantic import BaseModel, HttpUrl


class CloneRepositoryRequest(BaseModel):
    repository_url: HttpUrl


class WorkspaceResponse(BaseModel):
    workspace_id: str
    repository_path: str