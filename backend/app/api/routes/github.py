import uuid
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.identity import (
    GitHubInstallation,
    Repository,
    User,
)
from app.db.session import get_db
from app.core.config import settings
from app.schemas.github import (
    ConnectedRepositoryListResponse,
    ConnectedRepositoryResponse,
    GitHubInstallationListResponse,
    IssueListResponse,
    IssueResponse,
    RepositoryResponse,
)
from app.schemas.mapper import map_issue, map_repository
from app.services.auth.service import (
    auth_error,
    require_csrf,
    require_current_user,
)
from app.services.github.app_client import (
    GitHubAppClient,
    github_app_client,
)
from app.services.github.client import github_client
from app.services.github.installations import (
    InstallationService,
    installation_http_error,
)


router = APIRouter(
    prefix="/github",
    tags=["github"],
)


def get_github_app_client() -> GitHubAppClient:
    return github_app_client


@router.get(
    "/installations",
    response_model=GitHubInstallationListResponse,
)
async def list_installations(
    user: User = Depends(require_current_user),
    db: AsyncSession = Depends(get_db),
):
    installations = await InstallationService().list_installations(
        user_id=user.id,
        db=db,
    )
    count_rows = (
        await db.execute(
            select(
                Repository.installation_id,
                func.count(Repository.id).label(
                    "repository_count"
                ),
            )
            .where(Repository.access_status == "active")
            .group_by(Repository.installation_id)
        )
    ).all()
    counts = {
        row.installation_id: row.repository_count
        for row in count_rows
    }
    return {
        "installations": [
            serialize_installation(
                installation,
                counts.get(installation.id, 0),
            )
            for installation in installations
        ]
    }


@router.post(
    "/installations/{installation_id}/repositories/sync",
    response_model=ConnectedRepositoryListResponse,
)
async def sync_installation_repositories(
    installation_id: uuid.UUID,
    user: User = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
):
    service = InstallationService()
    installation = await service.get_user_installation(
        installation_id=installation_id,
        user_id=user.id,
        db=db,
    )
    repositories = await service.sync_repositories(
        installation=installation,
        db=db,
    )
    return {
        "repositories": [
            serialize_repository(item)
            for item in repositories
        ],
        "page": 1,
        "per_page": len(repositories) or 1,
        "total": len(repositories),
        "has_next": False,
    }


@router.get(
    "/repositories",
    response_model=ConnectedRepositoryListResponse,
)
async def list_connected_repositories(
    search: Annotated[
        str | None,
        Query(max_length=200),
    ] = None,
    installation_id: uuid.UUID | None = None,
    include_archived: bool = False,
    refresh: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 30,
    user: User = Depends(require_current_user),
    db: AsyncSession = Depends(get_db),
    github: GitHubAppClient = Depends(get_github_app_client),
):
    if refresh:
        service = InstallationService(github=github)
        if installation_id is not None:
            installations = [
                await service.get_user_installation(
                    installation_id=installation_id,
                    user_id=user.id,
                    db=db,
                )
            ]
        else:
            installations = [
                installation
                for installation in await service.list_installations(
                    user_id=user.id,
                    db=db,
                )
                if installation.status == "active"
            ]
        for installation in installations:
            await service.sync_repositories(
                installation=installation,
                db=db,
            )

    filters = [
        GitHubInstallation.user_id == user.id,
        GitHubInstallation.status == "active",
        Repository.access_status == "active",
    ]
    if installation_id is not None:
        filters.append(
            Repository.installation_id == installation_id
        )
    if not include_archived:
        filters.append(Repository.archived.is_(False))
    if search and search.strip():
        pattern = f"%{escape_like(search.strip())}%"
        filters.append(
            or_(
                Repository.full_name.ilike(pattern, escape="\\"),
                Repository.name.ilike(pattern, escape="\\"),
                Repository.owner.ilike(pattern, escape="\\"),
            )
        )

    base = (
        select(Repository)
        .join(
            GitHubInstallation,
            Repository.installation_id
            == GitHubInstallation.id,
        )
        .where(*filters)
    )
    total = int(
        await db.scalar(
            select(func.count()).select_from(base.subquery())
        )
        or 0
    )
    repositories = list(
        await db.scalars(
            base.order_by(Repository.full_name)
            .limit(per_page)
            .offset((page - 1) * per_page)
        )
    )
    return {
        "repositories": [
            serialize_repository(item)
            for item in repositories
        ],
        "page": page,
        "per_page": per_page,
        "total": total,
        "has_next": page * per_page < total,
    }


@router.get(
    "/repositories/{repository_id}",
    response_model=ConnectedRepositoryResponse,
)
async def get_connected_repository(
    repository_id: uuid.UUID,
    user: User = Depends(require_current_user),
    db: AsyncSession = Depends(get_db),
):
    repository, _ = await resolve_user_repository(
        repository_id=repository_id,
        user_id=user.id,
        db=db,
    )
    return serialize_repository(repository)


@router.get(
    "/repositories/{repository_id}/issues",
    response_model=IssueListResponse,
)
async def list_connected_repository_issues(
    repository_id: uuid.UUID,
    state: Annotated[
        str,
        Query(pattern="^(open|closed|all)$"),
    ] = "open",
    search: Annotated[
        str | None,
        Query(max_length=200),
    ] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 30,
    user: User = Depends(require_current_user),
    db: AsyncSession = Depends(get_db),
    github: GitHubAppClient = Depends(get_github_app_client),
):
    repository, installation = await resolve_user_repository(
        repository_id=repository_id,
        user_id=user.id,
        db=db,
    )
    try:
        payload = await github.list_issues(
            installation.github_installation_id,
            repository.owner,
            repository.name,
            state=state,
            per_page=per_page,
            page=page,
        )
    except httpx.HTTPStatusError as exc:
        raise installation_http_error(exc) from exc

    issues = [
        item
        for item in payload
        if "pull_request" not in item
    ]
    if search and search.strip():
        needle = search.casefold().strip()
        issues = [
            item
            for item in issues
            if needle
            in (
                f"{item.get('title', '')} "
                f"{item.get('body') or ''}"
            ).casefold()
        ]
    return {
        "issues": [
            map_issue(item)
            for item in issues
        ],
        "page": page,
        "per_page": per_page,
        "has_next": len(payload) == per_page,
    }


@router.get(
    "/repositories/{repository_id}/issues/{issue_number}",
    response_model=IssueResponse,
)
async def get_connected_repository_issue(
    repository_id: uuid.UUID,
    issue_number: int,
    user: User = Depends(require_current_user),
    db: AsyncSession = Depends(get_db),
    github: GitHubAppClient = Depends(get_github_app_client),
):
    repository, installation = await resolve_user_repository(
        repository_id=repository_id,
        user_id=user.id,
        db=db,
    )
    try:
        issue = await github.get_issue(
            installation.github_installation_id,
            repository.owner,
            repository.name,
            issue_number,
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise auth_error(
                status_code=404,
                code="ISSUE_NOT_FOUND",
                message="GitHub issue not found.",
            ) from exc
        raise installation_http_error(exc) from exc
    if "pull_request" in issue:
        raise auth_error(
            status_code=404,
            code="ISSUE_NOT_FOUND",
            message="GitHub issue not found.",
        )
    return map_issue(issue)


async def resolve_user_repository(
    *,
    repository_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
    require_active: bool = True,
) -> tuple[Repository, GitHubInstallation]:
    row = (
        await db.execute(
            select(Repository, GitHubInstallation)
            .join(
                GitHubInstallation,
                Repository.installation_id
                == GitHubInstallation.id,
            )
            .where(
                Repository.id == repository_id,
                GitHubInstallation.user_id == user_id,
            )
        )
    ).one_or_none()
    if row is None:
        raise auth_error(
            status_code=404,
            code="REPOSITORY_NOT_FOUND",
            message="Repository not found.",
        )
    repository, installation = row
    if require_active and (
        installation.status != "active"
        or repository.access_status != "active"
    ):
        raise auth_error(
            status_code=409,
            code="REPOSITORY_ACCESS_DENIED",
            message="Repository access was removed.",
        )
    return repository, installation


def serialize_installation(
    installation: GitHubInstallation,
    repository_count: int,
) -> dict:
    return {
        "id": str(installation.id),
        "github_installation_id": (
            installation.github_installation_id
        ),
        "account_id": installation.github_account_id,
        "account_login": installation.github_account_login,
        "account_type": installation.account_type,
        "target_type": installation.target_type,
        "repository_selection": installation.repository_selection,
        "status": installation.status,
        "suspended_at": (
            installation.suspended_at.isoformat()
            if installation.suspended_at
            else None
        ),
        "repository_count": repository_count,
    }


def serialize_repository(repository: Repository) -> dict:
    return {
        "id": str(repository.id),
        "installation_id": str(repository.installation_id),
        "github_repository_id": repository.github_repository_id,
        "owner": repository.owner,
        "name": repository.name,
        "full_name": repository.full_name,
        "private": repository.private,
        "archived": repository.archived,
        "disabled": repository.disabled,
        "default_branch": repository.default_branch,
        "html_url": repository.html_url,
        "permissions": repository.permissions_json or {},
        "access_status": repository.access_status,
        "last_synced_at": (
            repository.last_synced_at.isoformat()
            if repository.last_synced_at
            else None
        ),
    }


def escape_like(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


# Legacy owner/repository routes are retained for explicitly enabled local and
# evaluation workflows. They never expose tenant-owned repository records.
@router.get(
    "/repos/{owner}/{repo}",
    response_model=RepositoryResponse,
)
async def get_repository(owner: str, repo: str):
    require_legacy_github_api()
    try:
        data = await github_client.get_repository(owner, repo)
        return map_repository(data)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail="Repository not found",
            ) from exc
        raise


@router.get(
    "/repos/{owner}/{repo}/issues",
    response_model=list[IssueResponse],
)
async def list_repository_issues(
    owner: str,
    repo: str,
    state: str = "open",
):
    require_legacy_github_api()
    data = await github_client.list_issues(
        owner=owner,
        repo=repo,
        state=state,
    )
    return [
        map_issue(issue)
        for issue in data
        if "pull_request" not in issue
    ]


@router.get(
    "/repos/{owner}/{repo}/issues/{issue_number}",
    response_model=IssueResponse,
)
async def get_repository_issue(
    owner: str,
    repo: str,
    issue_number: int,
):
    require_legacy_github_api()
    try:
        data = await github_client.get_issue(
            owner,
            repo,
            issue_number,
        )
        if "pull_request" in data:
            raise HTTPException(
                status_code=404,
                detail="Issue not found",
            )
        return map_issue(data)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail="Issue not found",
            ) from exc
        raise


def require_legacy_github_api() -> None:
    if not settings.allow_legacy_unauthenticated_api:
        raise auth_error(
            status_code=401,
            code="AUTH_REQUIRED",
            message="Sign in with GitHub to continue.",
        )
