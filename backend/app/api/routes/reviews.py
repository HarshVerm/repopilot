from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
)
from app.services.tasks.workflow import (
    run_revision_background,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.indexing import WORKSPACES_DIR
from app.db.session import get_db
from app.schemas.reviews import (
    FinalReviewResponse,
    RejectReviewRequest,
    RejectTaskReviewRequest,
    RequestChangesRequest,
    TaskReviewActionRequest,
    ReviewDecisionResponse,
)
from app.services.auth.authorization import (
    authorize_task,
)
from app.services.auth.service import (
    AuthContext,
    get_optional_auth_context,
    validate_csrf_tokens,
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
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext | None = Depends(
        get_optional_auth_context
    ),
    service: ReviewService = Depends(
        get_review_service
    ),
):
    try:
        change_set = await service.load_change_set(
            change_set_id,
            db,
        )
        await authorize_task(
            task_id=change_set.task_id,
            auth=auth,
            db=db,
        )
        if auth is not None:
            validate_csrf_tokens(
                request=request,
                context=auth,
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
    auth: AuthContext | None = Depends(
        get_optional_auth_context
    ),
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
    await authorize_task(
        task_id=review.task_id,
        auth=auth,
        db=db,
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
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext | None = Depends(
        get_optional_auth_context
    ),
    service: ReviewService = Depends(
        get_review_service
    ),
):
    try:
        review = await service.load_review(
            review_id,
            db,
        )
        await authorize_task(
            task_id=review.task_id,
            auth=auth,
            db=db,
        )
        if auth is not None:
            validate_csrf_tokens(
                request=request,
                context=auth,
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
            reviewed_by_user_id=(
                auth.user.id
                if auth
                else None
            ),
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
    http_request: Request,
    request: RejectReviewRequest | None = None,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext | None = Depends(
        get_optional_auth_context
    ),
    service: ReviewService = Depends(
        get_review_service
    ),
):
    try:
        existing = await service.load_review(
            review_id,
            db,
        )
        await authorize_task(
            task_id=existing.task_id,
            auth=auth,
            db=db,
        )
        if auth is not None:
            validate_csrf_tokens(
                request=http_request,
                context=auth,
            )
        review = await service.reject_review(
            review_id=review_id,
            rejection_reason=(
                request.reason
                if request
                else None
            ),
            db=db,
            reviewed_by_user_id=(
                auth.user.id
                if auth
                else None
            ),
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


@router.post(
    "/tasks/{task_id}/review/approve",
    response_model=ReviewDecisionResponse,
)
async def approve_task_review(
    task_id: UUID,
    payload: TaskReviewActionRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext | None = Depends(
        get_optional_auth_context
    ),
    service: ReviewService = Depends(get_review_service),
):
    task = await authorize_task(
        task_id=task_id,
        auth=auth,
        db=db,
    )
    if auth is not None:
        validate_csrf_tokens(
            request=request,
            context=auth,
        )
    if task.active_review_id != payload.review_id:
        raise HTTPException(
            status_code=409,
            detail="The task changed while it was being reviewed",
        )
    review = await service.load_review(
        payload.review_id,
        db,
    )
    if review.task_id != task.id:
        raise HTTPException(
            status_code=404,
            detail="Task not found",
        )
    repository_path = (
        WORKSPACES_DIR / review.workspace_id / "repository"
    )
    try:
        result = await service.approve_review(
            review_id=review.id,
            repository_path=repository_path,
            db=db,
            reviewed_by_user_id=(
                auth.user.id if auth else None
            ),
            expected_change_set_id=payload.changeset_id,
            expected_diff_hash=payload.diff_hash,
        )
    except REVIEW_CONFLICT_ERRORS as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc
    return serialize_review_decision(result)


@router.post(
    "/tasks/{task_id}/review/request-changes",
    response_model=ReviewDecisionResponse,
)
async def request_task_review_changes(
    task_id: UUID,
    payload: RequestChangesRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext | None = Depends(
        get_optional_auth_context
    ),
    service: ReviewService = Depends(get_review_service),
):
    task = await authorize_task(
        task_id=task_id,
        auth=auth,
        db=db,
    )
    if auth is not None:
        validate_csrf_tokens(
            request=request,
            context=auth,
        )
    if task.active_review_id != payload.review_id:
        raise HTTPException(
            status_code=409,
            detail="The task changed while it was being reviewed",
        )
    review = await service.load_review(payload.review_id, db)
    if review.task_id != task.id:
        raise HTTPException(
            status_code=404,
            detail="Task not found",
        )
    try:
        result = await service.request_changes(
            review_id=review.id,
            feedback=payload.feedback,
            db=db,
            reviewed_by_user_id=(
                auth.user.id if auth else None
            ),
            expected_change_set_id=payload.changeset_id,
            expected_diff_hash=payload.diff_hash,
        )
    except ReviewStateError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc
    background_tasks.add_task(
        run_revision_background,
        str(task.id),
        str(review.change_set_id),
    )
    return serialize_review_decision(result)


@router.post(
    "/tasks/{task_id}/review/reject",
    response_model=ReviewDecisionResponse,
)
async def reject_task_review(
    task_id: UUID,
    payload: RejectTaskReviewRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext | None = Depends(
        get_optional_auth_context
    ),
    service: ReviewService = Depends(get_review_service),
):
    task = await authorize_task(
        task_id=task_id,
        auth=auth,
        db=db,
    )
    if auth is not None:
        validate_csrf_tokens(
            request=request,
            context=auth,
        )
    if task.active_review_id != payload.review_id:
        raise HTTPException(
            status_code=409,
            detail="The task changed while it was being reviewed",
        )
    review = await service.load_review(payload.review_id, db)
    if review.task_id != task.id:
        raise HTTPException(
            status_code=404,
            detail="Task not found",
        )
    try:
        result = await service.reject_review(
            review_id=review.id,
            rejection_reason=payload.reason,
            db=db,
            reviewed_by_user_id=(
                auth.user.id if auth else None
            ),
            expected_change_set_id=payload.changeset_id,
            expected_diff_hash=payload.diff_hash,
        )
    except ReviewStateError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc
    return serialize_review_decision(result)


REVIEW_CONFLICT_ERRORS = (
    ExecutionMismatchError,
    ReviewAlreadyExistsError,
    ReviewIntegrityError,
    ReviewNotEligibleError,
    ReviewStateError,
    WorkspaceDriftError,
)
