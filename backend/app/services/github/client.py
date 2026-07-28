import httpx

from app.core.config import settings


class GitHubClient:
    base_url = "https://api.github.com"

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        if settings.github_token:
            headers["Authorization"] = f"Bearer {settings.github_token}"

        return headers

    async def _get(
        self,
        path: str,
        params: dict[str, str] | None = None,
    ) -> dict | list[dict]:
        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._headers(),
            follow_redirects=True,
            timeout=10.0,
        ) as client:
            response = await client.get(path, params=params)
            response.raise_for_status()
            return response.json()

    async def get_repository(
        self,
        owner: str,
        repo: str,
    ) -> dict:
        data = await self._get(f"/repos/{owner}/{repo}")
        assert isinstance(data, dict)
        return data

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
