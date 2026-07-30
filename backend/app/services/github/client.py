# Module purpose: Implement client behavior for the GitHub integration domain.

import httpx

from app.core.config import settings
from app.services.hardening.retries import (
    RetryPolicy,
    retry_async,
)


# Purpose: Provide the git hub client integration boundary.
class GitHubClient:
    base_url = "https://api.github.com"

    # Purpose: Initialize git hub client state and dependencies.
    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._client = client

    # Purpose: Handle headers for the GitHub integration workflow.
    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        if settings.github_token:
            headers["Authorization"] = f"Bearer {settings.github_token}"

        return headers

    # Purpose: Handle timeout for the GitHub integration workflow.
    def _timeout(self) -> httpx.Timeout:
        return httpx.Timeout(
            timeout=settings.github_timeout_seconds,
            connect=settings.github_connect_timeout_seconds,
            read=settings.github_timeout_seconds,
            write=settings.github_timeout_seconds,
            pool=settings.github_connect_timeout_seconds,
        )

    # Purpose: Handle limits for the GitHub integration workflow.
    def _limits(self) -> httpx.Limits:
        return httpx.Limits(
            max_connections=settings.http_max_connections,
            max_keepalive_connections=(
                settings.http_max_keepalive_connections
            ),
        )

    # Purpose: Return client for the GitHub integration workflow.
    def get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=self._headers(),
                follow_redirects=True,
                timeout=self._timeout(),
                limits=self._limits(),
            )

        return self._client

    # Purpose: Handle close for the GitHub integration workflow.
    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # Purpose: Return GitHub integration for the GitHub integration workflow.
    async def _get(
        self,
        path: str,
        params: dict[str, str] | None = None,
    ) -> dict | list[dict]:
        # Purpose: Request GitHub integration for the GitHub integration workflow.
        async def request() -> dict | list[dict]:
            response = await self.get_client().get(
                path,
                params=params,
            )
            response.raise_for_status()
            return response.json()

        return await retry_async(
            request,
            policy=RetryPolicy(
                max_attempts=settings.provider_max_retries,
            ),
        )

    # Purpose: Return repository for the GitHub integration workflow.
    async def get_repository(
        self,
        owner: str,
        repo: str,
    ) -> dict:
        data = await self._get(f"/repos/{owner}/{repo}")
        assert isinstance(data, dict)
        return data

    # Purpose: List issues for the GitHub integration workflow.
    async def list_issues(
        self,
        owner: str,
        repo: str,
        state: str = "open",
    ) -> list[dict]:
        data = await self._get(
            f"/repos/{owner}/{repo}/issues",
            params={"state": state},
        )
        assert isinstance(data, list)
        return data

    # Purpose: Return issue for the GitHub integration workflow.
    async def get_issue(
        self,
        owner: str,
        repo: str,
        issue_number: int,
    ) -> dict:
        data = await self._get(f"/repos/{owner}/{repo}/issues/{issue_number}")
        assert isinstance(data, dict)
        return data


github_client = GitHubClient()
