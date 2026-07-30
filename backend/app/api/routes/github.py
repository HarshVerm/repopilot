# Module purpose: Define github HTTP API routes.

import uuid
from html import escape as escape_html
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
    CreateIssueRequest,
    GitHubInstallationListResponse,
    IssueListResponse,
    IssueResponse,
    RepositoryFileListResponse,
    RepositoryResponse,
)
from app.schemas.mapper import map_issue, map_repository
from app.observability.logging import (
    log_task_event,
    log_task_failure,
)
from app.services.auth.github_tokens import (
    GitHubUserAuthorizationRequired,
    GitHubUserAuthorizationUnavailable,
    GitHubUserTokenService,
)
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
from app.services.hardening.rate_limit import (
    enforce_rate_limit,
)


router = APIRouter(
    prefix="/github",
    tags=["github"],
)


# Purpose: Return github app client for the GitHub integration workflow.
def get_github_app_client() -> GitHubAppClient:
    return github_app_client


# Purpose: List installations for the GitHub integration workflow.
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


# Purpose: Synchronize installation repositories for the GitHub integration workflow.
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


# Purpose: List connected repositories for the GitHub integration workflow.
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


# Purpose: Return connected repository for the GitHub integration workflow.
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


# Purpose: List selectable files from a connected repository default branch.
@router.get(
    "/repositories/{repository_id}/files",
    response_model=RepositoryFileListResponse,
)
async def list_connected_repository_files(
    repository_id: uuid.UUID,
    search: Annotated[
        str | None,
        Query(max_length=200),
    ] = None,
    limit: Annotated[
        int,
        Query(ge=1, le=5000),
    ] = 5000,
    user: User = Depends(require_current_user),
    db: AsyncSession = Depends(get_db),
    github: GitHubAppClient = Depends(get_github_app_client),
):
    repository, installation = await resolve_user_repository(
        repository_id=repository_id,
        user_id=user.id,
        db=db,
    )
    files, github_truncated = await load_repository_file_paths(
        repository=repository,
        installation=installation,
        github=github,
    )
    if search and search.strip():
        needle = search.strip().casefold()
        files = [
            path
            for path in files
            if needle in path.casefold()
        ]
    total = len(files)
    return {
        "files": files[:limit],
        "total": total,
        "truncated": github_truncated or total > limit,
        "default_branch": repository.default_branch,
    }


# Purpose: List connected repository issues for the GitHub integration workflow.
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


# Purpose: Create a GitHub issue as the signed-in user.
@router.post(
    "/repositories/{repository_id}/issues",
    response_model=IssueResponse,
    status_code=201,
    dependencies=[
        Depends(enforce_rate_limit("issue_create")),
    ],
)
async def create_connected_repository_issue(
    repository_id: uuid.UUID,
    payload: CreateIssueRequest,
    user: User = Depends(require_csrf),
    db: AsyncSession = Depends(get_db),
    github: GitHubAppClient = Depends(get_github_app_client),
):
    repository, installation = await resolve_user_repository(
        repository_id=repository_id,
        user_id=user.id,
        db=db,
    )
    permissions = repository.permissions_json or {}
    if permissions.get("issues") is False:
        raise auth_error(
            status_code=403,
            code="GITHUB_ISSUE_WRITE_PERMISSION_REQUIRED",
            message=(
                "RepoPilot needs GitHub App Issues: read and write "
                "permission to create an issue."
            ),
            details={
                "required_permission": "issues:write",
            },
        )

    if payload.related_files:
        available_files, _ = await load_repository_file_paths(
            repository=repository,
            installation=installation,
            github=github,
        )
        missing_files = sorted(
            set(payload.related_files)
            - set(available_files)
        )
        if missing_files:
            raise auth_error(
                status_code=422,
                code="RELATED_FILES_INVALID",
                message=(
                    "One or more related files are no longer present "
                    "on the repository's default branch."
                ),
                details={
                    "files": missing_files[:20],
                },
            )

    body = build_issue_body(
        description=payload.description,
        related_files=payload.related_files,
    )
    if len(body) > settings.max_issue_body_chars:
        raise auth_error(
            status_code=422,
            code="GITHUB_ISSUE_BODY_TOO_LONG",
            message=(
                "The issue description and related file list are "
                f"limited to {settings.max_issue_body_chars} characters."
            ),
        )

    try:
        access_token = await GitHubUserTokenService().access_token(
            user_id=user.id,
            db=db,
        )
        issue = await github.create_issue_as_user(
            access_token=access_token,
            owner=repository.owner,
            repo=repository.name,
            title=payload.title,
            body=body,
        )
    except GitHubUserAuthorizationRequired as exc:
        raise auth_error(
            status_code=409,
            code="GITHUB_USER_AUTHORIZATION_REQUIRED",
            message=(
                "Reconnect your GitHub account before creating an "
                f"issue as @{user.github_login}."
            ),
            details={
                "setup_path": (
                    "/api/v1/auth/github/"
                    "user-authorization/setup"
                ),
            },
        ) from exc
    except GitHubUserAuthorizationUnavailable as exc:
        raise auth_error(
            status_code=502,
            code="GITHUB_USER_AUTHORIZATION_UNAVAILABLE",
            message=(
                "GitHub user authorization could not be refreshed. "
                "Try creating the issue again."
            ),
        ) from exc
    except httpx.HTTPStatusError as exc:
        log_task_failure(
            "github.issue_creation_failed",
            exc,
            repository_id=str(repository.id),
            repository=repository.full_name,
            github_status=exc.response.status_code,
        )
        raise github_issue_creation_http_error(exc) from exc
    except httpx.HTTPError as exc:
        log_task_failure(
            "github.issue_creation_failed",
            exc,
            repository_id=str(repository.id),
            repository=repository.full_name,
        )
        raise auth_error(
            status_code=502,
            code="GITHUB_UNAVAILABLE",
            message="GitHub could not create the issue. Try again.",
        ) from exc

    log_task_event(
        "github.issue_created",
        user_id=str(user.id),
        repository_id=str(repository.id),
        repository=repository.full_name,
        issue_number=issue.get("number"),
        related_file_count=len(payload.related_files),
        issue_actor=user.github_login,
    )
    return map_issue(issue)


# Purpose: Return connected repository issue for the GitHub integration workflow.
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


# Purpose: Load and validate blob paths from a repository's default branch.
async def load_repository_file_paths(
    *,
    repository: Repository,
    installation: GitHubInstallation,
    github: GitHubAppClient,
) -> tuple[list[str], bool]:
    try:
        payload = await github.list_repository_tree(
            installation.github_installation_id,
            repository.owner,
            repository.name,
            repository.default_branch,
        )
    except httpx.HTTPStatusError as exc:
        raise installation_http_error(exc) from exc
    except httpx.HTTPError as exc:
        raise auth_error(
            status_code=502,
            code="GITHUB_UNAVAILABLE",
            message="GitHub could not load repository files. Try again.",
        ) from exc
    files = sorted(
        {
            path
            for item in payload.get("tree", [])
            if item.get("type") == "blob"
            and isinstance(item.get("path"), str)
            and (
                path := validated_repository_file_path(
                    item["path"]
                )
            )
            is not None
        }
    )
    return files, bool(payload.get("truncated"))


# Purpose: Reject unsafe or unusable repository paths before displaying them.
def validated_repository_file_path(
    value: str,
) -> str | None:
    if (
        not value
        or len(value) > 1000
        or value.startswith("/")
        or any(character in value for character in "\0\r\n")
    ):
        return None
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return None
    return value


# Purpose: Build the GitHub issue body with optional related-file context.
def build_issue_body(
    *,
    description: str,
    related_files: list[str],
) -> str:
    body = description.strip()
    if not related_files:
        return body
    file_list = "\n".join(
        f"- <code>{escape_html(path)}</code>"
        for path in related_files
    )
    return (
        f"{body}\n\n---\n\n"
        "### Related files\n\n"
        f"{file_list}"
    )


# Purpose: Convert GitHub issue-creation failures into actionable API errors.
def github_issue_creation_http_error(
    exc: httpx.HTTPStatusError,
) -> HTTPException:
    status_code = exc.response.status_code
    if (
        status_code == 429
        or exc.response.headers.get(
            "x-ratelimit-remaining"
        )
        == "0"
    ):
        return auth_error(
            status_code=429,
            code="GITHUB_RATE_LIMITED",
            message="GitHub rate-limited issue creation. Try again later.",
        )
    if status_code == 401:
        return auth_error(
            status_code=409,
            code="GITHUB_USER_AUTHORIZATION_REQUIRED",
            message=(
                "Reconnect your GitHub account before creating an issue."
            ),
            details={
                "setup_path": (
                    "/api/v1/auth/github/"
                    "user-authorization/setup"
                ),
            },
        )
    if status_code == 403:
        return auth_error(
            status_code=403,
            code="GITHUB_ISSUE_WRITE_PERMISSION_REQUIRED",
            message=(
                "RepoPilot needs GitHub App Issues: read and write "
                "permission to create an issue."
            ),
            details={
                "required_permission": "issues:write",
            },
        )
    if status_code == 404:
        return auth_error(
            status_code=404,
            code="REPOSITORY_NOT_FOUND",
            message=(
                "GitHub could not find this repository for the "
                "signed-in user."
            ),
        )
    if status_code == 410:
        return auth_error(
            status_code=409,
            code="GITHUB_ISSUES_DISABLED",
            message="GitHub Issues are disabled for this repository.",
        )
    if status_code == 422:
        return auth_error(
            status_code=422,
            code="GITHUB_ISSUE_INVALID",
            message=(
                "GitHub rejected the issue. Check the title and "
                "description, then try again."
            ),
        )
    return auth_error(
        status_code=502,
        code="GITHUB_UNAVAILABLE",
        message="GitHub could not create the issue. Try again.",
    )


# Purpose: Resolve user repository for the GitHub integration workflow.
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


# Purpose: Serialize installation for the GitHub integration workflow.
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


# Purpose: Serialize repository for the GitHub integration workflow.
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


# Purpose: Escape like for the GitHub integration workflow.
def escape_like(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


# Legacy owner/repository routes are retained for explicitly enabled local and
# evaluation workflows. They never expose tenant-owned repository records.
# Purpose: Return repository for the GitHub integration workflow.
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


# Purpose: List repository issues for the GitHub integration workflow.
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


# Purpose: Return repository issue for the GitHub integration workflow.
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


# Purpose: Require legacy github api, raising an error when unavailable.
def require_legacy_github_api() -> None:
    if not settings.allow_legacy_unauthenticated_api:
        raise auth_error(
            status_code=401,
            code="AUTH_REQUIRED",
            message="Sign in with GitHub to continue.",
        )
