# Module purpose: Define retrieval HTTP API routes.

from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.indexing import WORKSPACES_DIR
from app.db.session import get_db
from app.schemas.retrieval import (
    RetrievalBuildResponse,
    RetrievalSearchRequest,
    RetrievalSearchResponse,
)
from app.services.embeddings.client import (
    OpenAIEmbeddingClient,
)
from app.services.hardening.validation import (
    InputLimitError,
)
from app.services.retrieval.service import (
    build_retrieval_index,
    hybrid_search,
)
from app.services.tasks.service import TaskService
from app.services.auth.authorization import authorize_task
from app.services.auth.service import (
    AuthContext,
    get_optional_auth_context,
    validate_csrf_tokens,
)


router = APIRouter(
    prefix="/retrieval",
    tags=["retrieval"],
)


# Purpose: Return embedding client for the retrieval workflow.
def get_embedding_client():
    return OpenAIEmbeddingClient()


# Purpose: Build retrieval for the retrieval workflow.
@router.post(
    "/{workspace_id}/build",
    response_model=RetrievalBuildResponse,
)
async def build_retrieval(
    workspace_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext | None = Depends(
        get_optional_auth_context
    ),
    embedding_client=Depends(
        get_embedding_client
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
    task = await TaskService().find_task_by_workspace(
        workspace_id=str(workspace_id),
        db=db,
    )
    await authorize_task(
        task_id=task.id if task else None,
        auth=auth,
        db=db,
    )
    if auth is not None:
        validate_csrf_tokens(
            request=request,
            context=auth,
        )

    result = await build_retrieval_index(
        workspace_id=str(workspace_id),
        repository_path=repository_path,
        db=db,
        embedding_client=embedding_client,
    )

    return {
        "workspace_id": str(workspace_id),
        **result,
    }


# Purpose: Handle search retrieval for the retrieval workflow.
@router.post(
    "/{workspace_id}/search",
    response_model=RetrievalSearchResponse,
)
async def search_retrieval(
    workspace_id: UUID,
    request: RetrievalSearchRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext | None = Depends(
        get_optional_auth_context
    ),
    embedding_client=Depends(
        get_embedding_client
    ),
):
    query = request.query.strip()
    task = await TaskService().find_task_by_workspace(
        workspace_id=str(workspace_id),
        db=db,
    )
    await authorize_task(
        task_id=task.id if task else None,
        auth=auth,
        db=db,
    )
    if auth is not None:
        validate_csrf_tokens(
            request=http_request,
            context=auth,
        )

    if not query:
        raise HTTPException(
            status_code=422,
            detail="Query must not be blank",
        )

    try:
        return await hybrid_search(
            workspace_id=str(workspace_id),
            query=query,
            top_k=request.top_k,
            db=db,
            embedding_client=embedding_client,
            debug=request.debug,
        )
    except InputLimitError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc
