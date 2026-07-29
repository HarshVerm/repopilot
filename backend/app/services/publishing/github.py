from dataclasses import dataclass
from typing import Protocol

import httpx

from app.services.publishing.authentication import (
    GitHubCredentials,
)
from app.services.publishing.git import (
    sanitize_error,
)


class PullRequestCreationError(RuntimeError):
    pass


class GitHubPublisherError(RuntimeError):
    pass


@dataclass(frozen=True)
class RepositoryMetadata:
    default_branch: str


@dataclass(frozen=True)
class PullRequestMetadata:
    number: int
    url: str
    head_sha: str | None = None


class GitHubPublisher(Protocol):
    async def get_repository(
        self,
        *,
        owner: str,
        repo: str,
        credentials: GitHubCredentials | None,
    ) -> RepositoryMetadata:
        ...

    async def find_open_pull_request(
        self,
        *,
        owner: str,
        repo: str,
        head_branch: str,
        base_branch: str,
        credentials: GitHubCredentials | None,
    ) -> PullRequestMetadata | None:
        ...

    async def create_pull_request(
        self,
        *,
        owner: str,
        repo: str,
        head_branch: str,
        base_branch: str,
        title: str,
        body: str,
        credentials: GitHubCredentials | None,
    ) -> PullRequestMetadata:
        ...


class GitHubApiPublisher:
    base_url = "https://api.github.com"

    async def get_repository(
        self,
        *,
        owner: str,
        repo: str,
        credentials: GitHubCredentials | None,
    ) -> RepositoryMetadata:
        data = await self.request(
            "GET",
            f"/repos/{owner}/{repo}",
            credentials=credentials,
        )

        return RepositoryMetadata(
            default_branch=data["default_branch"]
        )

    async def find_open_pull_request(
        self,
        *,
        owner: str,
        repo: str,
        head_branch: str,
        base_branch: str,
        credentials: GitHubCredentials | None,
    ) -> PullRequestMetadata | None:
        data = await self.request(
            "GET",
            f"/repos/{owner}/{repo}/pulls",
            credentials=credentials,
            params={
                "state": "open",
                "head": f"{owner}:{head_branch}",
                "base": base_branch,
            },
        )

        if not data:
            return None

        pull = data[0]
        return pull_request_from_json(
            pull
        )

    async def create_pull_request(
        self,
        *,
        owner: str,
        repo: str,
        head_branch: str,
        base_branch: str,
        title: str,
        body: str,
        credentials: GitHubCredentials | None,
    ) -> PullRequestMetadata:
        try:
            data = await self.request(
                "POST",
                f"/repos/{owner}/{repo}/pulls",
                credentials=credentials,
                json={
                    "title": title,
                    "body": body,
                    "head": head_branch,
                    "base": base_branch,
                },
            )
        except GitHubPublisherError as exc:
            raise PullRequestCreationError(
                str(exc)
            ) from exc

        return pull_request_from_json(
            data
        )

    async def request(
        self,
        method: str,
        path: str,
        *,
        credentials: GitHubCredentials | None,
        params: dict | None = None,
        json: dict | None = None,
    ):
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        if credentials:
            headers["Authorization"] = (
                f"Bearer {credentials.token}"
            )

        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            follow_redirects=True,
            timeout=15.0,
        ) as client:
            try:
                response = await client.request(
                    method,
                    path,
                    params=params,
                    json=json,
                )
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise GitHubPublisherError(
                    sanitize_error(
                        exc.__class__.__name__,
                        secrets=(
                            (credentials.token,)
                            if credentials
                            else ()
                        ),
                    )
                ) from exc

            return response.json()


def pull_request_from_json(
    data: dict,
) -> PullRequestMetadata:
    return PullRequestMetadata(
        number=data["number"],
        url=data.get("html_url") or data.get("url") or "",
        head_sha=(
            data.get("head", {}).get("sha")
            if isinstance(
                data.get("head"),
                dict,
            )
            else None
        ),
    )
