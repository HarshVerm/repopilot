from pydantic import BaseModel


class RepositoryResponse(BaseModel):
    id: int
    name: str
    full_name: str
    description: str | None
    private: bool
    default_branch: str
    clone_url: str
    language: str | None
    stars: int


class IssueResponse(BaseModel):
    id: int
    number: int
    title: str
    body: str | None
    state: str
    html_url: str
    comments: int
    labels: list[str]