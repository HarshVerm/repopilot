# Module purpose: Define validated github API payload schemas.

from pydantic import BaseModel, Field


# Purpose: Validate and represent repository response data.
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
    archived: bool = False
    disabled: bool = False


# Purpose: Validate and represent issue response data.
class IssueResponse(BaseModel):
    id: int
    number: int
    title: str
    body: str | None
    state: str
    html_url: str
    comments: int
    labels: list[str]
    author: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


# Purpose: Validate and represent git hub installation response data.
class GitHubInstallationResponse(BaseModel):
    id: str
    github_installation_id: int
    account_id: int
    account_login: str
    account_type: str
    target_type: str | None
    repository_selection: str
    status: str
    suspended_at: str | None
    repository_count: int = 0


# Purpose: Validate and represent git hub installation list response data.
class GitHubInstallationListResponse(BaseModel):
    installations: list[GitHubInstallationResponse]


# Purpose: Validate and represent connected repository response data.
class ConnectedRepositoryResponse(BaseModel):
    id: str
    installation_id: str
    github_repository_id: int
    owner: str
    name: str
    full_name: str
    private: bool
    archived: bool
    disabled: bool
    default_branch: str
    html_url: str
    permissions: dict[str, bool] = Field(default_factory=dict)
    access_status: str
    last_synced_at: str | None


# Purpose: Validate and represent connected repository list response data.
class ConnectedRepositoryListResponse(BaseModel):
    repositories: list[ConnectedRepositoryResponse]
    page: int
    per_page: int
    total: int
    has_next: bool


# Purpose: Validate and represent issue list response data.
class IssueListResponse(BaseModel):
    issues: list[IssueResponse]
    page: int
    per_page: int
    has_next: bool
