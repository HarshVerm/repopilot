from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.indexing import WORKSPACES_DIR
from app.db.models.execution_run import ExecutionRun
from app.db.session import get_db
from app.schemas.debugging import (
    DebugAttemptResponse,
    DebugRunResponse,
)
from app.services.debugging.orchestrator import (
    DebugOrchestrator,
    serialize_debug_attempt_detail,
    serialize_debug_workflow,
)
from app.services.debugging.policy import (
    DebugNotEligibleError,
)


router = APIRouter(
    tags=["debugging"],
)


def get_debug_orchestrator() -> DebugOrchestrator:
    return DebugOrchestrator()


@router.post(
    "/execution-runs/{execution_run_id}/debug",
    response_model=DebugRunResponse,
)
async def debug_execution_run(
    execution_run_id: UUID,
    db: AsyncSession = Depends(get_db),
    orchestrator: DebugOrchestrator = Depends(
        get_debug_orchestrator
    ),
):
    run = await db.get(
        ExecutionRun,
        execution_run_id,
    )

    if run is None:
        raise HTTPException(
            status_code=404,
            detail="ExecutionRun not found",
        )

    if run.status in {
        "passed",
        "pending",
        "running",
    }:
        raise HTTPException(
            status_code=409,
            detail="ExecutionRun is not eligible for debugging",
        )

    repository_path = (
        WORKSPACES_DIR
        / run.workspace_id
        / "repository"
    )

    try:
        result = await orchestrator.debug_execution_run(
            execution_run_id=execution_run_id,
            repository_path=repository_path,
            db=db,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
    except DebugNotEligibleError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    return serialize_debug_workflow(
        result
    )


@router.get(
    "/debug-attempts/{debug_attempt_id}",
    response_model=DebugAttemptResponse,
)
async def get_debug_attempt(
    debug_attempt_id: UUID,
    db: AsyncSession = Depends(get_db),
    orchestrator: DebugOrchestrator = Depends(
        get_debug_orchestrator
    ),
):
    attempt = await orchestrator.get_debug_attempt(
        debug_attempt_id=debug_attempt_id,
        db=db,
    )

    if attempt is None:
        raise HTTPException(
            status_code=404,
            detail="DebugAttempt not found",
        )

    return serialize_debug_attempt_detail(
        attempt
    )
