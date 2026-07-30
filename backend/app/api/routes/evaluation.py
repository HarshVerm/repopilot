# Module purpose: Define evaluation HTTP API routes.

from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.evaluation_run import EvaluationRun
from app.db.session import get_db
from app.evaluation.runner import (
    EvaluationRunError,
    EvaluationRunner,
)
from app.schemas.evaluation import (
    EvaluationRunRecordResponse,
    EvaluationRunRequest,
    EvaluationRunResponse,
)
from app.services.hardening.rate_limit import (
    enforce_rate_limit,
)
from app.services.auth.service import (
    AuthContext,
    auth_error,
    get_optional_auth_context,
    validate_csrf_tokens,
)


router = APIRouter(
    prefix="/evaluations",
    tags=["evaluation"],
)


# Purpose: Run evaluation for the evaluation workflow.
@router.post(
    "",
    response_model=EvaluationRunResponse,
    dependencies=[
        Depends(
            enforce_rate_limit(
                "evaluation_launch"
            )
        )
    ],
)
async def run_evaluation(
    request: EvaluationRunRequest,
    http_request: Request,
    auth: AuthContext | None = Depends(
        get_optional_auth_context
    ),
):
    authorize_evaluation_api(auth)
    if auth is not None:
        validate_csrf_tokens(
            request=http_request,
            context=auth,
        )
    if request.live and not settings.evaluation_mode:
        raise HTTPException(
            status_code=403,
            detail="Live evaluation requires EVALUATION_MODE=true",
        )

    try:
        return await EvaluationRunner().run(
            suite_version=request.suite,
            task_id=request.task,
            difficulty=request.difficulty,
            category=request.category,
            max_tasks=request.max_tasks,
            dry_run=request.dry_run or not request.live,
            live=request.live,
            mark_baseline=request.mark_baseline,
        )
    except EvaluationRunError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc


# Purpose: Return evaluation run for the evaluation workflow.
@router.get(
    "/{evaluation_run_id}",
    response_model=EvaluationRunRecordResponse,
)
async def get_evaluation_run(
    evaluation_run_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext | None = Depends(
        get_optional_auth_context
    ),
):
    authorize_evaluation_api(auth)
    run = await db.get(
        EvaluationRun,
        evaluation_run_id,
    )

    if run is None:
        raise HTTPException(
            status_code=404,
            detail="EvaluationRun not found",
        )

    return EvaluationRunRecordResponse(
        run_id=str(run.id),
        suite_name=run.suite_name,
        suite_version=run.suite_version,
        status=run.status,
        report=run.report_json,
    )


# Purpose: Authorize evaluation api for the evaluation workflow.
def authorize_evaluation_api(
    auth: AuthContext | None,
) -> None:
    if (
        auth is None
        and not settings.allow_legacy_unauthenticated_api
    ):
        raise auth_error(
            status_code=401,
            code="AUTH_REQUIRED",
            message="Sign in with GitHub to continue.",
        )
