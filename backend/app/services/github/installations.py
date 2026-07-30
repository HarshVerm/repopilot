# Module purpose: Implement installations behavior for the GitHub integration domain.

import uuid
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.identity import (
    GitHubInstallation,
    Repository,
)
from app.services.auth.service import auth_error
from app.services.github.app_client import (
    GitHubAppClient,
    GitHubAppConfigurationError,
    github_app_client,
    missing_github_app_settings,
)
from app.services.github.permissions import (
    repository_capabilities_from_app_permissions,
)


# Purpose: Coordinate installation operations.
class InstallationService:
    # Purpose: Initialize installation service state and dependencies.
    def __init__(
        self,
        *,
        github: GitHubAppClient | None = None,
    ) -> None:
        self.github = github or github_app_client

    # Purpose: Synchronize installations for the GitHub integration workflow.
    async def sync_installations(
        self,
        *,
        user_id: uuid.UUID,
        installations: list[dict],
        db: AsyncSession,
    ) -> list[GitHubInstallation]:
        records = []
        seen: set[int] = set()
        for payload in installations:
            seen.add(int(payload["id"]))
            records.append(
                await self.upsert_installation(
                    user_id=user_id,
                    payload=payload,
                    db=db,
                    commit=False,
                )
            )
        existing = await db.scalars(
            select(GitHubInstallation).where(
                GitHubInstallation.user_id == user_id
            )
        )
        for installation in existing:
            if installation.github_installation_id not in seen:
                installation.status = "removed"
                repositories = await db.scalars(
                    select(Repository).where(
                        Repository.installation_id
                        == installation.id
                    )
                )
                for repository in repositories:
                    repository.access_status = "removed"
        await db.commit()
        return records

    # Purpose: Connect installation for the GitHub integration workflow.
    async def connect_installation(
        self,
        *,
        user_id: uuid.UUID,
        github_installation_id: int,
        db: AsyncSession,
    ) -> GitHubInstallation:
        try:
            payload = await self.github.get_installation(
                github_installation_id
            )
        except httpx.HTTPStatusError as exc:
            raise installation_http_error(exc) from exc
        except GitHubAppConfigurationError as exc:
            raise github_app_configuration_error() from exc
        installation = await self.upsert_installation(
            user_id=user_id,
            payload=payload,
            db=db,
            commit=True,
        )
        await self.sync_repositories(
            installation=installation,
            db=db,
            app_permissions=payload.get(
                "permissions"
            ),
        )
        return installation

    # Purpose: Create or update installation for the GitHub integration workflow.
    async def upsert_installation(
        self,
        *,
        user_id: uuid.UUID,
        payload: dict,
        db: AsyncSession,
        commit: bool,
    ) -> GitHubInstallation:
        external_id = int(payload["id"])
        installation = await db.scalar(
            select(GitHubInstallation).where(
                GitHubInstallation.user_id == user_id,
                GitHubInstallation.github_installation_id
                == external_id,
            )
        )
        account = payload.get("account") or {}
        if installation is None:
            installation = GitHubInstallation(
                user_id=user_id,
                github_installation_id=external_id,
                github_account_id=int(account["id"]),
                github_account_login=str(
                    account.get("login") or account.get("slug") or ""
                ),
                account_type=str(account.get("type") or "User"),
            )
            db.add(installation)
        installation.github_account_id = int(account["id"])
        installation.github_account_login = str(
            account.get("login") or account.get("slug") or ""
        )
        installation.account_type = str(
            account.get("type") or "User"
        )
        installation.target_type = payload.get("target_type")
        installation.repository_selection = str(
            payload.get("repository_selection") or "selected"
        )
        installation.suspended_at = parse_datetime(
            payload.get("suspended_at")
        )
        installation.status = (
            "suspended"
            if installation.suspended_at
            else "active"
        )
        if commit:
            await db.commit()
            await db.refresh(installation)
        return installation

    # Purpose: List installations for the GitHub integration workflow.
    async def list_installations(
        self,
        *,
        user_id: uuid.UUID,
        db: AsyncSession,
    ) -> list[GitHubInstallation]:
        return list(
            await db.scalars(
                select(GitHubInstallation)
                .where(
                    GitHubInstallation.user_id == user_id
                )
                .order_by(
                    GitHubInstallation.github_account_login
                )
            )
        )

    # Purpose: Return user installation for the GitHub integration workflow.
    async def get_user_installation(
        self,
        *,
        installation_id: uuid.UUID,
        user_id: uuid.UUID,
        db: AsyncSession,
        require_active: bool = True,
    ) -> GitHubInstallation:
        installation = await db.scalar(
            select(GitHubInstallation).where(
                GitHubInstallation.id == installation_id,
                GitHubInstallation.user_id == user_id,
            )
        )
        if installation is None:
            raise auth_error(
                status_code=404,
                code="GITHUB_INSTALLATION_NOT_FOUND",
                message="GitHub installation not found.",
            )
        if require_active and installation.status != "active":
            raise auth_error(
                status_code=409,
                code="GITHUB_INSTALLATION_REMOVED",
                message="Repository access was removed or suspended.",
            )
        return installation

    # Purpose: Synchronize repositories for the GitHub integration workflow.
    async def sync_repositories(
        self,
        *,
        installation: GitHubInstallation,
        db: AsyncSession,
        app_permissions: dict | None = None,
    ) -> list[Repository]:
        if installation.status != "active":
            raise auth_error(
                status_code=409,
                code="GITHUB_INSTALLATION_REMOVED",
                message="Repository access was removed or suspended.",
            )
        try:
            if app_permissions is None:
                installation_payload = (
                    await self.github.get_installation(
                        installation.github_installation_id
                    )
                )
                app_permissions = dict(
                    installation_payload.get(
                        "permissions"
                    )
                    or {}
                )
            repository_capabilities = (
                repository_capabilities_from_app_permissions(
                    app_permissions
                )
            )
            repository_payloads: list[dict] = []
            for page in range(1, 101):
                payload = (
                    await self.github.list_installation_repositories(
                        installation.github_installation_id,
                        per_page=100,
                        page=page,
                    )
                )
                page_items = list(
                    payload.get("repositories", [])
                )
                repository_payloads.extend(page_items)
                total_count = int(
                    payload.get("total_count")
                    or len(repository_payloads)
                )
                if (
                    len(page_items) < 100
                    or len(repository_payloads) >= total_count
                ):
                    break
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {401, 403, 404}:
                installation.status = (
                    "removed"
                    if exc.response.status_code == 404
                    else "permission_error"
                )
                await db.commit()
            raise installation_http_error(exc) from exc
        except GitHubAppConfigurationError as exc:
            raise github_app_configuration_error() from exc

        now = datetime.now(UTC)
        seen: set[int] = set()
        records: list[Repository] = []
        for item in repository_payloads:
            external_id = int(item["id"])
            seen.add(external_id)
            repository = await db.scalar(
                select(Repository).where(
                    Repository.installation_id == installation.id,
                    Repository.github_repository_id == external_id,
                )
            )
            if repository is None:
                repository = Repository(
                    installation_id=installation.id,
                    github_repository_id=external_id,
                    owner="",
                    name="",
                    full_name="",
                    html_url="",
                )
                db.add(repository)
            owner = item.get("owner") or {}
            repository.owner = str(owner.get("login") or "")
            repository.name = str(item["name"])
            repository.full_name = str(item["full_name"])
            repository.private = bool(item.get("private", False))
            repository.archived = bool(item.get("archived", False))
            repository.disabled = bool(item.get("disabled", False))
            repository.default_branch = str(
                item.get("default_branch") or "main"
            )
            repository.html_url = str(item.get("html_url") or "")
            repository.clone_url = item.get("clone_url")
            repository.permissions_json = dict(
                repository_capabilities
            )
            repository.access_status = "active"
            repository.last_synced_at = now
            records.append(repository)

        existing = await db.scalars(
            select(Repository).where(
                Repository.installation_id == installation.id
            )
        )
        for repository in existing:
            if repository.github_repository_id not in seen:
                repository.access_status = "removed"
                repository.last_synced_at = now
        await db.commit()
        for repository in records:
            await db.refresh(repository)
        return records


# Purpose: Parse datetime for the GitHub integration workflow.
def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


# Purpose: Handle installation http error for the GitHub integration workflow.
def installation_http_error(
    exc: httpx.HTTPStatusError,
):
    status = exc.response.status_code
    try:
        github_message = str(
            exc.response.json().get("message") or ""
        ).casefold()
    except ValueError:
        github_message = ""
    if status == 403 and (
        "approval" in github_message
        or "organization owner" in github_message
    ):
        return auth_error(
            status_code=403,
            code="GITHUB_ORG_APPROVAL_REQUIRED",
            message=(
                "A GitHub organization owner must approve RepoPilot."
            ),
        )
    if status == 404:
        return auth_error(
            status_code=409,
            code="GITHUB_INSTALLATION_REMOVED",
            message="The GitHub App installation is no longer available.",
        )
    if status == 403:
        rate_limited = exc.response.headers.get(
            "X-RateLimit-Remaining"
        ) == "0"
        return auth_error(
            status_code=429 if rate_limited else 403,
            code=(
                "GITHUB_RATE_LIMITED"
                if rate_limited
                else "GITHUB_PERMISSION_DENIED"
            ),
            message=(
                "GitHub rate limit reached. Try again later."
                if rate_limited
                else "GitHub App permissions are insufficient."
            ),
        )
    return auth_error(
        status_code=502,
        code="GITHUB_UNAVAILABLE",
        message="GitHub could not complete the request.",
    )


# Purpose: Handle github app configuration error for the GitHub integration workflow.
def github_app_configuration_error():
    return auth_error(
        status_code=503,
        code="GITHUB_APP_NOT_CONFIGURED",
        message=(
            "Complete the RepoPilot GitHub App configuration "
            "before connecting repositories."
        ),
        details={
            "missing_settings": missing_github_app_settings(),
        },
    )
