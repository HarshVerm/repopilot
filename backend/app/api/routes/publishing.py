from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.indexing import WORKSPACES_DIR
from app.db.session import get_db
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
    db: AsyncSession = Depends(get_db),
    service: PublicationService = Depends(
        get_publication_service
    ),
):
    try:
        review = await service.review_service.load_review(
            review_id,
            db,
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

    return serialize_publication(
        publication
    )


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
