from pydantic import BaseModel


class CurrentUserResponse(BaseModel):
    user_id: str
    github_user_id: int
    github_login: str
    github_name: str | None
    github_avatar_url: str | None
    github_email: str | None


class LogoutResponse(BaseModel):
    logged_out: bool


class GitHubSetupResponse(BaseModel):
    url: str
