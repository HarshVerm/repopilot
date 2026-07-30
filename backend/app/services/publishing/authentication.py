# Module purpose: Implement authentication behavior for the publication domain.

from dataclasses import dataclass
from typing import Protocol

from app.core.config import settings


# Purpose: Encapsulate git hub credentials behavior for the publication domain.
@dataclass(frozen=True)
class GitHubCredentials:
    username: str
    token: str


# Purpose: Define the interface required from git hub authenticator implementations.
class GitHubAuthenticator(Protocol):
    # Purpose: Return credentials for the publication workflow.
    async def get_credentials(
        self,
        *,
        owner: str,
        repo: str,
    ) -> GitHubCredentials | None:
        ...


# Purpose: Encapsulate settings git hub authenticator behavior for the publication domain.
class SettingsGitHubAuthenticator:
    # Purpose: Return credentials for the publication workflow.
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
