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

from app.agents.coder.agent import (
    AgentsCoderRunner,
)
from app.agents.coder.service import (
    CodingService,
    PlanNotApprovedError,
    serialize_change_set,
    serialize_change_set_diff,
)
from app.api.routes.indexing import WORKSPACES_DIR
from app.api.routes.plans import (
    get_github_client,
)
from app.api.routes.retrieval import (
    get_embedding_client,
)
from app.db.models.execution_plan import (
    ExecutionPlan,
)
from app.db.session import get_db
from app.schemas.changes import (
    ChangeSetDiffResponse,
    ImplementPlanResponse,
)
from app.services.changes.git import (
    DirtyWorkspaceError,
)
from app.services.hardening.rate_limit import (
    enforce_rate_limit,
)
from app.services.planning.service import (
    issue_query_text,
)
from app.services.retrieval.service import (
    hybrid_search,
)
from app.services.tasks.locking import (
    TaskOperationConflict,
)
from app.services.tasks.service import (
    TaskService,
    task_issue_snapshot,
)
from app.services.auth.authorization import (
    authorize_task,
)
from app.services.auth.service import (
    AuthContext,
    get_optional_auth_context,
    validate_csrf_tokens,
)


router = APIRouter(
    tags=["coding"],
)


def get_coder_runner():
    return AgentsCoderRunner()


@router.post(
    "/plans/{plan_id}/implement",
    response_model=ImplementPlanResponse,
    dependencies=[
        Depends(
            enforce_rate_limit(
                "coding"
            )
        )
    ],
)
async def implement_plan(
    plan_id: UUID,
    request: Request,
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
    coder_runner=Depends(
        get_coder_runner
    ),
):
    plan = await db.get(
        ExecutionPlan,
        plan_id,
    )

    if plan is None:
        raise HTTPException(
            status_code=404,
            detail="Plan not found",
        )
    task = await authorize_task(
        task_id=plan.task_id,
        auth=auth,
        db=db,
    )
    if auth is not None:
        validate_csrf_tokens(
            request=request,
            context=auth,
        )

    if plan.status != "approved":
        raise HTTPException(
            status_code=409,
            detail="Only approved plans can be implemented",
        )

    repository_path = (
        WORKSPACES_DIR
        / plan.workspace_id
        / "repository"
    )

    if not repository_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Workspace not found",
        )

    if task is not None and task.user_id is not None:
        issue = task_issue_snapshot(task)
    else:
        try:
            issue = await github.get_issue(
                plan.repository_owner,
                plan.repository_name,
                plan.issue_number,
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
        issue["number"] = plan.issue_number
    retrieval_started = time.perf_counter()
    retrieval_result = await hybrid_search(
        workspace_id=plan.workspace_id,
        query=issue_query_text(issue),
        top_k=10,
        db=db,
        embedding_client=embedding_client,
        debug=False,
    )
    if plan.task_id is not None:
        await TaskService().record_event(
            task_id=plan.task_id,
            event_type="retrieval.completed",
            db=db,
            metadata={
                "workspace_id": plan.workspace_id,
                "phase": "coding",
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

    try:
        change_set = await CodingService(
            coder_runner=coder_runner
        ).implement_plan(
            plan=plan,
            repository_path=repository_path,
            issue=issue,
            context_pack=retrieval_result["context"],
            db=db,
        )
    except PlanNotApprovedError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc
    except DirtyWorkspaceError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc
    except TaskOperationConflict as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    return serialize_change_set(
        change_set
    )


@router.get(
    "/change-sets/{change_set_id}/diff",
    response_model=ChangeSetDiffResponse,
)
async def get_change_set_diff(
    change_set_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext | None = Depends(
        get_optional_auth_context
    ),
):
    change_set = await CodingService().get_change_set(
        change_set_id=change_set_id,
        db=db,
    )

    if change_set is None:
        raise HTTPException(
            status_code=404,
            detail="ChangeSet not found",
        )
    await authorize_task(
        task_id=change_set.task_id,
        auth=auth,
        db=db,
    )

    return serialize_change_set_diff(
        change_set
    )
