# Module purpose: Define plans HTTP API routes.

import time
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
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
    task_issue_snapshot,
)
from app.services.tasks.state_machine import (
    CREATED,
    INDEXED,
    REPOSITORY_PREPARING,
    REPOSITORY_READY,
    RETRIEVING,
    TaskTransitionError,
)
from app.services.auth.authorization import authorize_task
from app.services.auth.service import (
    AuthContext,
    get_optional_auth_context,
    validate_csrf_tokens,
)


router = APIRouter(
    tags=["plans"],
)


# Purpose: Return github client for the HTTP API workflow.
def get_github_client():
    return github_client


# Purpose: Return planner runner for the HTTP API workflow.
def get_planner_runner():
    return AgentsPlannerRunner()


PRE_PLAN_TASK_STATES = {
    CREATED,
    REPOSITORY_PREPARING,
    REPOSITORY_READY,
    INDEXED,
}


# Purpose: Create workspace plan for the HTTP API workflow.
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
    http_request: Request,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext | None = Depends(
        get_optional_auth_context
    ),
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
    workspace_task = await TaskService().find_task_by_workspace(
        workspace_id=str(workspace_id),
        db=db,
    )
    if workspace_task is not None:
        await authorize_task(
            task_id=workspace_task.id,
            auth=auth,
            db=db,
        )
    else:
        await authorize_task(
            task_id=None,
            auth=auth,
            db=db,
        )
    if auth is not None:
        validate_csrf_tokens(
            request=http_request,
            context=auth,
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

    if workspace_task is not None:
        if (
            request.owner != workspace_task.repository_owner
            or request.repo != workspace_task.repository_name
            or request.issue_number != workspace_task.issue_number
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Plan request does not match the task's immutable "
                    "repository and issue snapshot"
                ),
            )
        issue = task_issue_snapshot(workspace_task)
    else:
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
        task = workspace_task or (
            await task_service.find_active_task(
                owner=request.owner,
                repo=request.repo,
                issue_number=request.issue_number,
                db=db,
                user_id=(
                    auth.user.id
                    if auth
                    else None
                ),
            )
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
                issue_snapshot=issue,
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


# Purpose: Return plan for the HTTP API workflow.
@router.get(
    "/plans/{plan_id}",
    response_model=PlanResponse,
)
async def get_plan(
    plan_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext | None = Depends(
        get_optional_auth_context
    ),
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
    await authorize_task(
        task_id=plan.task_id,
        auth=auth,
        db=db,
    )

    return serialize_plan(plan)


# Purpose: Approve plan for the HTTP API workflow.
@router.post(
    "/plans/{plan_id}/approve",
    response_model=PlanStatusResponse,
)
async def approve_plan(
    plan_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext | None = Depends(
        get_optional_auth_context
    ),
):
    try:
        current_plan = await PlannerService().get_plan(
            plan_id=plan_id,
            db=db,
        )
        if current_plan is None:
            raise KeyError(plan_id)
        await authorize_task(
            task_id=current_plan.task_id,
            auth=auth,
            db=db,
        )
        if auth is not None:
            validate_csrf_tokens(
                request=request,
                context=auth,
            )
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


# Purpose: Reject plan for the HTTP API workflow.
@router.post(
    "/plans/{plan_id}/reject",
    response_model=PlanStatusResponse,
)
async def reject_plan(
    plan_id: UUID,
    http_request: Request,
    request: RejectPlanRequest | None = None,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext | None = Depends(
        get_optional_auth_context
    ),
):
    try:
        current_plan = await PlannerService().get_plan(
            plan_id=plan_id,
            db=db,
        )
        if current_plan is None:
            raise KeyError(plan_id)
        await authorize_task(
            task_id=current_plan.task_id,
            auth=auth,
            db=db,
        )
        if auth is not None:
            validate_csrf_tokens(
                request=http_request,
                context=auth,
            )
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
