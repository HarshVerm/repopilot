from fastapi import APIRouter, HTTPException

from app.schemas.workspace import (
    CloneRepositoryRequest,
    WorkspaceResponse,
)
from app.services.workspace.manager import (
    workspace_manager,
)


router = APIRouter(
    prefix="/workspaces",
    tags=["workspaces"],
)


@router.post(
    "/clone",
    response_model=WorkspaceResponse,
)
async def clone_repository(
    request: CloneRepositoryRequest,
):
    try:
        workspace_id, path = (
            await workspace_manager.clone_repository(
                str(request.repository_url)
            )
        )

        return WorkspaceResponse(
            workspace_id=workspace_id,
            repository_path=str(path),
        )

    except RuntimeError as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )