from datetime import UTC, datetime, timedelta
from urllib.parse import quote

import httpx
import jwt
from jwt.exceptions import PyJWTError

from app.core.config import settings


class GitHubAppConfigurationError(RuntimeError):
    pass


def missing_github_app_settings() -> list[str]:
    private_key_configured = bool(
        settings.github_app_private_key
        or settings.github_app_private_key_path
    )
    configured_values = {
        "GITHUB_APP_ID": settings.github_app_id,
        "GITHUB_APP_CLIENT_ID": settings.github_app_client_id,
        "GITHUB_APP_CLIENT_SECRET": settings.github_app_client_secret,
        "GITHUB_APP_PRIVATE_KEY": private_key_configured,
        "GITHUB_APP_SLUG": settings.github_app_slug,
    }
    return [
        name
        for name, value in configured_values.items()
        if not value
    ]


class GitHubAppClient:
    base_url = "https://api.github.com"

    def private_key(self) -> str:
        if settings.github_app_private_key_path:
            try:
                value = (
                    settings.github_app_private_key_path
                    .expanduser()
                    .read_text(encoding="utf-8")
                )
            except OSError as exc:
                raise GitHubAppConfigurationError(
                    "GitHub App private key file could not be read"
                ) from exc
        else:
            value = settings.github_app_private_key or ""

        private_key = value.replace("\\n", "\n").strip()
        if (
            not private_key.startswith("-----BEGIN ")
            or "-----END " not in private_key
        ):
            raise GitHubAppConfigurationError(
                "GitHub App private key is not a valid PEM"
            )
        return private_key

    def app_jwt(self) -> str:
        missing_settings = [
            name
            for name in missing_github_app_settings()
            if name in {
                "GITHUB_APP_ID",
                "GITHUB_APP_PRIVATE_KEY",
            }
        ]
        if missing_settings:
            raise GitHubAppConfigurationError(
                "Missing GitHub App settings: "
                + ", ".join(missing_settings)
            )
        now = datetime.now(UTC)
        try:
            return jwt.encode(
                {
                    "iat": int(
                        (now - timedelta(seconds=60)).timestamp()
                    ),
                    "exp": int(
                        (now + timedelta(minutes=9)).timestamp()
                    ),
                    "iss": settings.github_app_id,
                },
                self.private_key(),
                algorithm="RS256",
            )
        except (
            PyJWTError,
            TypeError,
            ValueError,
        ) as exc:
            raise GitHubAppConfigurationError(
                "GitHub App private key could not sign a JWT"
            ) from exc

    def headers(self, token: str) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def app_request(
        self,
        method: str,
        path: str,
        **kwargs,
    ) -> httpx.Response:
        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=settings.github_timeout_seconds,
            follow_redirects=True,
        ) as client:
            response = await client.request(
                method,
                path,
                headers=self.headers(self.app_jwt()),
                **kwargs,
            )
            response.raise_for_status()
            return response

    async def get_installation(
        self,
        github_installation_id: int,
    ) -> dict:
        response = await self.app_request(
            "GET",
            f"/app/installations/{github_installation_id}",
        )
        return response.json()

    async def create_installation_token(
        self,
        github_installation_id: int,
    ) -> str:
        response = await self.app_request(
            "POST",
            f"/app/installations/{github_installation_id}/access_tokens",
        )
        token = response.json().get("token")
        if not isinstance(token, str) or not token:
            raise GitHubAppConfigurationError(
                "GitHub did not return an installation token"
            )
        return token

    async def installation_request(
        self,
        *,
        github_installation_id: int,
        method: str,
        path: str,
        params: dict[str, str | int] | None = None,
        json: dict | None = None,
    ) -> httpx.Response:
        token = await self.create_installation_token(
            github_installation_id
        )
        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=settings.github_timeout_seconds,
            follow_redirects=True,
        ) as client:
            response = await client.request(
                method,
                path,
                headers=self.headers(token),
                params=params,
                json=json,
            )
            response.raise_for_status()
            return response

    async def list_installation_repositories(
        self,
        github_installation_id: int,
        *,
        per_page: int = 100,
        page: int = 1,
    ) -> dict:
        response = await self.installation_request(
            github_installation_id=github_installation_id,
            method="GET",
            path="/installation/repositories",
            params={
                "per_page": per_page,
                "page": page,
            },
        )
        return response.json()

    async def get_repository(
        self,
        github_installation_id: int,
        owner: str,
        repo: str,
    ) -> dict:
        response = await self.installation_request(
            github_installation_id=github_installation_id,
            method="GET",
            path=repository_path(owner, repo),
        )
        return response.json()

    async def list_issues(
        self,
        github_installation_id: int,
        owner: str,
        repo: str,
        *,
        state: str = "open",
        per_page: int = 30,
        page: int = 1,
    ) -> list[dict]:
        response = await self.installation_request(
            github_installation_id=github_installation_id,
            method="GET",
            path=f"{repository_path(owner, repo)}/issues",
            params={
                "state": state,
                "per_page": per_page,
                "page": page,
                "sort": "updated",
                "direction": "desc",
            },
        )
        return list(response.json())

    async def get_issue(
        self,
        github_installation_id: int,
        owner: str,
        repo: str,
        issue_number: int,
    ) -> dict:
        response = await self.installation_request(
            github_installation_id=github_installation_id,
            method="GET",
            path=(
                f"{repository_path(owner, repo)}/issues/"
                f"{issue_number}"
            ),
        )
        return response.json()

    async def get_branch_head_sha(
        self,
        github_installation_id: int,
        owner: str,
        repo: str,
        branch: str,
    ) -> str:
        response = await self.installation_request(
            github_installation_id=github_installation_id,
            method="GET",
            path=(
                f"{repository_path(owner, repo)}/branches/"
                f"{quote(branch, safe='')}"
            ),
        )
        return str(response.json()["commit"]["sha"])


github_app_client = GitHubAppClient()


def repository_path(owner: str, repo: str) -> str:
    return (
        f"/repos/{quote(owner, safe='')}/"
        f"{quote(repo, safe='')}"
    )
