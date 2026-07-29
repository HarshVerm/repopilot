from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
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
from app.services.planning.service import (
    issue_query_text,
)
from app.services.retrieval.service import (
    hybrid_search,
)


router = APIRouter(
    tags=["coding"],
)


def get_coder_runner():
    return AgentsCoderRunner()


@router.post(
    "/plans/{plan_id}/implement",
    response_model=ImplementPlanResponse,
)
async def implement_plan(
    plan_id: UUID,
    db: AsyncSession = Depends(get_db),
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
    retrieval_result = await hybrid_search(
        workspace_id=plan.workspace_id,
        query=issue_query_text(issue),
        top_k=10,
        db=db,
        embedding_client=embedding_client,
        debug=False,
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

    return serialize_change_set_diff(
        change_set
    )
