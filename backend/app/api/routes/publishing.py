from uuid import UUID

import httpx
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.indexing import WORKSPACES_DIR
from app.db.session import get_db
from app.db.models.identity import Repository
from app.schemas.publishing import (
    PublicationResponse,
)
from app.services.changes.git import (
    GitCommandError,
)
from app.services.hardening.rate_limit import (
    enforce_rate_limit,
)
from app.services.publishing.git import (
    GitPushError,
)
from app.services.publishing.github import (
    GitHubPublisherError,
    PullRequestCreationError,
)
from app.services.publishing.integrity import (
    PublicationError,
)
from app.services.publishing.naming import (
    BranchNameError,
)
from app.services.publishing.service import (
    PublicationService,
    serialize_publication,
)
from app.services.reviews.service import (
    ExecutionMismatchError,
    ReviewIntegrityError,
    ReviewNotEligibleError,
    ReviewStateError,
    WorkspaceDriftError,
)
from app.services.auth.authorization import (
    authorize_task,
)
from app.services.auth.service import (
    AuthContext,
    auth_error,
    get_optional_auth_context,
    validate_csrf_tokens,
)
from app.api.routes.github import (
    resolve_user_repository,
)
from app.services.github.app_client import (
    GitHubAppClient,
    github_app_client,
)
from app.services.github.permissions import (
    missing_publication_permissions,
    repository_capabilities_from_app_permissions,
)
from app.services.github.installations import (
    installation_http_error,
)
from app.observability.logging import (
    log_task_event,
)


router = APIRouter(
    tags=["publishing"],
)


def get_publication_service() -> PublicationService:
    return PublicationService()


@router.post(
    "/reviews/{review_id}/publish",
    response_model=PublicationResponse,
    dependencies=[
        Depends(
            enforce_rate_limit(
                "publication"
            )
        )
    ],
)
async def publish_review(
    review_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext | None = Depends(
        get_optional_auth_context
    ),
    service: PublicationService = Depends(
        get_publication_service
    ),
):
    try:
        review = await service.review_service.load_review(
            review_id,
            db,
        )
        task = await authorize_task(
            task_id=review.task_id,
            auth=auth,
            db=db,
        )
        if auth is not None:
            validate_csrf_tokens(
                request=request,
                context=auth,
            )
        native = await native_publication_context(
            task=task,
            auth=auth,
            review=review,
            db=db,
        )
        repository_path = (
            WORKSPACES_DIR
            / review.workspace_id
            / "repository"
        )
        publication = await service.publish_review(
            review_id=review_id,
            repository_path=repository_path,
            db=db,
            task_id=(task.id if task else None),
            **native,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
    except PUBLISH_CONFLICT_ERRORS as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    return serialize_publication(
        publication
    )


@router.get(
    "/publications/{publication_id}",
    response_model=PublicationResponse,
)
async def get_publication(
    publication_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext | None = Depends(
        get_optional_auth_context
    ),
    service: PublicationService = Depends(
        get_publication_service
    ),
):
    publication = await service.get_publication(
        publication_id=publication_id,
        db=db,
    )

    if publication is None:
        raise HTTPException(
            status_code=404,
            detail="Publication not found",
        )
    await authorize_task(
        task_id=publication.task_id,
        auth=auth,
        db=db,
    )

    return serialize_publication(
        publication
    )


@router.get(
    "/reviews/{review_id}/publication",
    response_model=PublicationResponse,
)
async def get_review_publication(
    review_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext | None = Depends(
        get_optional_auth_context
    ),
    service: PublicationService = Depends(
        get_publication_service
    ),
):
    publication = await service.get_publication_by_review(
        review_id=review_id,
        db=db,
    )

    if publication is None:
        raise HTTPException(
            status_code=404,
            detail="Publication not found",
        )
    await authorize_task(
        task_id=publication.task_id,
        auth=auth,
        db=db,
    )

    return serialize_publication(
        publication
    )


@router.post(
    "/tasks/{task_id}/publish",
    response_model=PublicationResponse,
    dependencies=[
        Depends(
            enforce_rate_limit(
                "publication"
            )
        )
    ],
)
async def publish_task(
    task_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext | None = Depends(
        get_optional_auth_context
    ),
    service: PublicationService = Depends(
        get_publication_service
    ),
):
    task = await authorize_task(
        task_id=task_id,
        auth=auth,
        db=db,
    )
    if task is None:
        raise HTTPException(
            status_code=404,
            detail="Task not found",
        )
    if auth is not None:
        validate_csrf_tokens(
            request=request,
            context=auth,
        )
    if task.active_review_id is None:
        raise auth_error(
            status_code=409,
            code="PUBLICATION_NOT_APPROVED",
            message="Approve the latest diff before publishing.",
        )
    review = await service.review_service.load_review(
        task.active_review_id,
        db,
    )
    native = await native_publication_context(
        task=task,
        auth=auth,
        review=review,
        db=db,
    )
    try:
        publication = await service.publish_review(
            review_id=review.id,
            repository_path=(
                WORKSPACES_DIR
                / review.workspace_id
                / "repository"
            ),
            db=db,
            task_id=task.id,
            **native,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
    except PUBLISH_CONFLICT_ERRORS as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc
    return serialize_publication(publication)


async def native_publication_context(
    *,
    task,
    auth: AuthContext | None,
    review,
    db: AsyncSession,
) -> dict:
    if task is None or task.repository_id is None:
        return {}
    if auth is None:
        raise auth_error(
            status_code=401,
            code="AUTH_REQUIRED",
            message="Sign in with GitHub to publish.",
        )
    repository, installation = await resolve_user_repository(
        repository_id=task.repository_id,
        user_id=auth.user.id,
        db=db,
    )
    try:
        installation_metadata = (
            await github_app_client.get_installation(
                installation.github_installation_id
            )
        )
        app_permissions = dict(
            installation_metadata.get(
                "permissions"
            )
            or {}
        )
        missing_permissions = (
            missing_publication_permissions(
                app_permissions
            )
        )
        if missing_permissions:
            log_task_event(
                "publication.authorization_denied",
                task_id=str(task.id),
                repository_id=str(repository.id),
                installation_id=str(
                    installation.id
                ),
                reason="missing_github_app_permissions",
                missing_permissions=missing_permissions,
                granted_permissions=app_permissions,
            )
            raise auth_error(
                status_code=403,
                code="GITHUB_PERMISSION_DENIED",
                message=(
                    "GitHub App installation must grant "
                    "Contents: Read and write and "
                    "Pull requests: Read and write."
                ),
                details={
                    "missing_permissions": (
                        missing_permissions
                    ),
                },
            )
        metadata = await github_app_client.get_repository(
            installation.github_installation_id,
            repository.owner,
            repository.name,
        )
        default_branch = str(
            metadata.get("default_branch")
            or repository.default_branch
        )
        remote_base_sha = (
            await github_app_client.get_branch_head_sha(
                installation.github_installation_id,
                repository.owner,
                repository.name,
                default_branch,
            )
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in {401, 403, 404}:
            installation.status = (
                "removed"
                if exc.response.status_code == 404
                else "permission_error"
            )
            repository.access_status = (
                "removed"
                if exc.response.status_code == 404
                else "permission_error"
            )
            await db.commit()
        raise installation_http_error(exc) from exc
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        raise auth_error(
            status_code=502,
            code="GITHUB_UNAVAILABLE",
            message="GitHub repository authorization could not be verified.",
        ) from exc
    if remote_base_sha != review.base_commit_sha:
        raise auth_error(
            status_code=409,
            code="BASE_BRANCH_CHANGED",
            message=(
                "The base branch changed after this diff was generated. "
                "Revalidate the task before publishing."
            ),
        )
    owner = str(
        (metadata.get("owner") or {}).get("login")
        or repository.owner
    )
    repository.owner = owner
    repository.name = str(
        metadata.get("name") or repository.name
    )
    repository.full_name = str(
        metadata.get("full_name") or repository.full_name
    )
    repository.default_branch = default_branch
    repository.permissions_json = (
        repository_capabilities_from_app_permissions(
            app_permissions
        )
    )
    await db.commit()
    log_task_event(
        "publication.authorization_verified",
        task_id=str(task.id),
        repository_id=str(repository.id),
        installation_id=str(installation.id),
        github_installation_id=(
            installation.github_installation_id
        ),
        repository=repository.full_name,
        required_permissions=[
            "contents:write",
            "pull_requests:write",
        ],
    )
    return {
        "github_installation_id": (
            installation.github_installation_id
        ),
        "installation_id": installation.id,
        "repository_id": repository.id,
    }


PUBLISH_CONFLICT_ERRORS = (
    BranchNameError,
    ExecutionMismatchError,
    GitCommandError,
    GitPushError,
    GitHubPublisherError,
    PublicationError,
    PullRequestCreationError,
    ReviewIntegrityError,
    ReviewNotEligibleError,
    ReviewStateError,
    WorkspaceDriftError,
)
