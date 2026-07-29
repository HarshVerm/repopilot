from dataclasses import dataclass
from typing import Protocol

from app.core.config import settings


@dataclass(frozen=True)
class GitHubCredentials:
    username: str
    token: str


class GitHubAuthenticator(Protocol):
    async def get_credentials(
        self,
        *,
        owner: str,
        repo: str,
    ) -> GitHubCredentials | None:
        ...


class SettingsGitHubAuthenticator:
    async def get_credentials(
        self,
        *,
        owner: str,
        repo: str,
    ) -> GitHubCredentials | None:
        if not settings.github_token:
            return None

        return GitHubCredentials(
            username="x-access-token",
            token=settings.github_token,
        )
