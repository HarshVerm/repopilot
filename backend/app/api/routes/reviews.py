from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.indexing import WORKSPACES_DIR
from app.db.session import get_db
from app.schemas.reviews import (
    FinalReviewResponse,
    RejectReviewRequest,
    ReviewDecisionResponse,
)
from app.services.reviews.service import (
    ExecutionMismatchError,
    ReviewAlreadyExistsError,
    ReviewIntegrityError,
    ReviewNotEligibleError,
    ReviewService,
    ReviewStateError,
    WorkspaceDriftError,
    serialize_final_review,
    serialize_review_decision,
)


router = APIRouter(
    tags=["reviews"],
)


def get_review_service() -> ReviewService:
    return ReviewService()


@router.post(
    "/change-sets/{change_set_id}/review",
    response_model=FinalReviewResponse,
)
async def create_final_review(
    change_set_id: UUID,
    db: AsyncSession = Depends(get_db),
    service: ReviewService = Depends(
        get_review_service
    ),
):
    try:
        change_set = await service.load_change_set(
            change_set_id,
            db,
        )
        repository_path = (
            WORKSPACES_DIR
            / change_set.workspace_id
            / "repository"
        )
        review = await service.create_review(
            change_set_id=change_set_id,
            repository_path=repository_path,
            db=db,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
    except REVIEW_CONFLICT_ERRORS as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    return serialize_final_review(
        review
    )


@router.get(
    "/reviews/{review_id}",
    response_model=FinalReviewResponse,
)
async def get_final_review(
    review_id: UUID,
    db: AsyncSession = Depends(get_db),
    service: ReviewService = Depends(
        get_review_service
    ),
):
    review = await service.get_review(
        review_id=review_id,
        db=db,
    )

    if review is None:
        raise HTTPException(
            status_code=404,
            detail="FinalReview not found",
        )

    return serialize_final_review(
        review
    )


@router.post(
    "/reviews/{review_id}/approve",
    response_model=ReviewDecisionResponse,
)
async def approve_final_review(
    review_id: UUID,
    db: AsyncSession = Depends(get_db),
    service: ReviewService = Depends(
        get_review_service
    ),
):
    try:
        review = await service.load_review(
            review_id,
            db,
        )
        repository_path = (
            WORKSPACES_DIR
            / review.workspace_id
            / "repository"
        )
        approved = await service.approve_review(
            review_id=review_id,
            repository_path=repository_path,
            db=db,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
    except REVIEW_CONFLICT_ERRORS as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    return serialize_review_decision(
        approved
    )


@router.post(
    "/reviews/{review_id}/reject",
    response_model=ReviewDecisionResponse,
)
async def reject_final_review(
    review_id: UUID,
    request: RejectReviewRequest | None = None,
    db: AsyncSession = Depends(get_db),
    service: ReviewService = Depends(
        get_review_service
    ),
):
    try:
        review = await service.reject_review(
            review_id=review_id,
            rejection_reason=(
                request.reason
                if request
                else None
            ),
            db=db,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
    except ReviewStateError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    return serialize_review_decision(
        review
    )


REVIEW_CONFLICT_ERRORS = (
    ExecutionMismatchError,
    ReviewAlreadyExistsError,
    ReviewIntegrityError,
    ReviewNotEligibleError,
    ReviewStateError,
    WorkspaceDriftError,
)
