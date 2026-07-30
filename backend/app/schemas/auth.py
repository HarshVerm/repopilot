# Module purpose: Define validated auth API payload schemas.

from datetime import datetime

from pydantic import BaseModel


# Purpose: Validate and represent current user response data.
class CurrentUserResponse(BaseModel):
    user_id: str
    github_user_id: int
    github_login: str
    github_name: str | None
    github_avatar_url: str | None
    github_email: str | None


# Purpose: Validate and represent logout response data.
class LogoutResponse(BaseModel):
    logged_out: bool


# Purpose: Validate and represent git hub setup response data.
class GitHubSetupResponse(BaseModel):
    url: str


# Purpose: Validate and represent git hub user authorization response data.
class GitHubUserAuthorizationResponse(BaseModel):
    connected: bool
    status: str
    attributed_login: str
    access_token_expires_at: datetime | None
    refresh_token_expires_at: datetime | None
