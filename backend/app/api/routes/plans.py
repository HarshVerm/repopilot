import time
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.indexing import WORKSPACES_DIR
from app.api.routes.retrieval import (
    get_embedding_client,
)
from app.db.session import get_db
from app.schemas.planning import (
    CreatePlanRequest,
    PlanResponse,
    PlanStatusResponse,
    RejectPlanRequest,
)
from app.services.github.client import (
    github_client,
)
from app.services.hardening.rate_limit import (
    enforce_rate_limit,
)
from app.services.planning.agent import (
    AgentsPlannerRunner,
)
from app.services.planning.service import (
    PlanStateError,
    PlannerService,
    PlanningError,
    issue_query_text,
    serialize_plan,
)
from app.services.planning.validation import (
    PlanValidationError,
)
from app.services.planning.workspace import (
    workspace_matches_repository,
)
from app.services.retrieval.service import (
    hybrid_search,
)
from app.services.tasks.failures import (
    RETRIEVAL_ERROR,
)
from app.services.tasks.service import (
    TaskService,
    TaskValidationError,
)
from app.services.tasks.state_machine import (
    CREATED,
    INDEXED,
    REPOSITORY_PREPARING,
    REPOSITORY_READY,
    RETRIEVING,
    TaskTransitionError,
)


router = APIRouter(
    tags=["plans"],
)


def get_github_client():
    return github_client


def get_planner_runner():
    return AgentsPlannerRunner()


PRE_PLAN_TASK_STATES = {
    CREATED,
    REPOSITORY_PREPARING,
    REPOSITORY_READY,
    INDEXED,
}


@router.post(
    "/workspaces/{workspace_id}/plan",
    response_model=PlanResponse,
    dependencies=[
        Depends(
            enforce_rate_limit(
                "planning"
            )
        )
    ],
)
async def create_workspace_plan(
    workspace_id: UUID,
    request: CreatePlanRequest,
    db: AsyncSession = Depends(get_db),
    embedding_client=Depends(
        get_embedding_client
    ),
    github=Depends(
        get_github_client
    ),
    planner_runner=Depends(
        get_planner_runner
    ),
):
    repository_path = (
        WORKSPACES_DIR
        / str(workspace_id)
        / "repository"
    )

    if not repository_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Workspace not found",
        )

    repository_match = workspace_matches_repository(
        repository_path=repository_path,
        owner=request.owner,
        repo=request.repo,
    )

    if repository_match is False:
        raise HTTPException(
            status_code=409,
            detail="Workspace repository does not match requested repository",
        )

    try:
        issue = await github.get_issue(
            request.owner,
            request.repo,
            request.issue_number,
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail="Issue not found",
            )

        raise HTTPException(
            status_code=502,
            detail="GitHub issue retrieval failed",
        ) from exc

    issue["number"] = request.issue_number
    task_service = TaskService()

    try:
        task = await task_service.find_active_task(
            owner=request.owner,
            repo=request.repo,
            issue_number=request.issue_number,
            db=db,
        )

        if (
            task is None
            or task.status
            not in PRE_PLAN_TASK_STATES
        ):
            task = await task_service.create_task(
                owner=request.owner,
                repo=request.repo,
                issue_number=request.issue_number,
                db=db,
                reuse_active=False,
            )

        task = await task_service.attach_workspace(
            task_id=task.id,
            workspace_id=str(workspace_id),
            db=db,
        )
        task = await task_service.transition_task(
            task_id=task.id,
            new_status=RETRIEVING,
            db=db,
            event_type="retrieval.started",
            metadata={
                "workspace_id": str(workspace_id)
            },
        )
    except (
        TaskValidationError,
        TaskTransitionError,
    ) as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    retrieval_started = time.perf_counter()

    try:
        retrieval_result = await hybrid_search(
            workspace_id=str(workspace_id),
            query=issue_query_text(issue),
            top_k=10,
            db=db,
            embedding_client=embedding_client,
            debug=False,
        )
        await task_service.record_event(
            task_id=task.id,
            event_type="retrieval.completed",
            db=db,
            metadata={
                "workspace_id": str(workspace_id),
                "final_result_count": len(
                    retrieval_result.get(
                        "results",
                        [],
                    )
                ),
                "context_token_count": (
                    retrieval_result.get(
                        "context",
                        {},
                    ).get(
                        "estimated_tokens",
                        0,
                    )
                ),
                "files_included": len(
                    retrieval_result.get(
                        "context",
                        {},
                    ).get(
                        "files",
                        [],
                    )
                ),
                "latency_ms": (
                    time.perf_counter()
                    - retrieval_started
                )
                * 1000,
            },
            commit=True,
        )
        plan = await PlannerService(
            planner_runner=planner_runner
        ).create_plan(
            workspace_id=str(workspace_id),
            repository_path=repository_path,
            owner=request.owner,
            repo=request.repo,
            issue=issue,
            context_pack=retrieval_result["context"],
            db=db,
            task_id=task.id,
        )
    except PlanValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc
    except PlanningError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        await task_service.set_failure(
            task_id=task.id,
            db=db,
            failure_category=RETRIEVAL_ERROR,
            error=exc,
            event_type="retrieval.failed",
        )
        raise

    return serialize_plan(plan)


@router.get(
    "/plans/{plan_id}",
    response_model=PlanResponse,
)
async def get_plan(
    plan_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    plan = await PlannerService().get_plan(
        plan_id=plan_id,
        db=db,
    )

    if plan is None:
        raise HTTPException(
            status_code=404,
            detail="Plan not found",
        )

    return serialize_plan(plan)


@router.post(
    "/plans/{plan_id}/approve",
    response_model=PlanStatusResponse,
)
async def approve_plan(
    plan_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    try:
        plan = await PlannerService().approve_plan(
            plan_id=plan_id,
            db=db,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail="Plan not found",
        ) from exc
    except PlanStateError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    return PlanStatusResponse(
        plan_id=str(plan.id),
        status=plan.status,
        rejection_reason=plan.rejection_reason,
    )


@router.post(
    "/plans/{plan_id}/reject",
    response_model=PlanStatusResponse,
)
async def reject_plan(
    plan_id: UUID,
    request: RejectPlanRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    try:
        plan = await PlannerService().reject_plan(
            plan_id=plan_id,
            reason=(
                request.reason
                if request is not None
                else None
            ),
            db=db,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail="Plan not found",
        ) from exc
    except PlanStateError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    return PlanStatusResponse(
        plan_id=str(plan.id),
        status=plan.status,
        rejection_reason=plan.rejection_reason,
    )
