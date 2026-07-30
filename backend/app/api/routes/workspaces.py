# Module purpose: Define workspaces HTTP API routes.

from fastapi import APIRouter, Depends, HTTPException

from app.schemas.workspace import (
    CloneRepositoryRequest,
    WorkspaceResponse,
)
from app.services.workspace.manager import (
    workspace_manager,
)
from app.core.config import settings
from app.services.auth.service import (
    AuthContext,
    auth_error,
    get_optional_auth_context,
)


router = APIRouter(
    prefix="/workspaces",
    tags=["workspaces"],
)


# Purpose: Clone repository for the HTTP API workflow.
@router.post(
    "/clone",
    response_model=WorkspaceResponse,
)
async def clone_repository(
    request: CloneRepositoryRequest,
    auth: AuthContext | None = Depends(
        get_optional_auth_context
    ),
):
    if auth is not None or not settings.allow_legacy_unauthenticated_api:
        raise auth_error(
            status_code=403,
            code="REPOSITORY_ACCESS_DENIED",
            message=(
                "Create a task from an authorized GitHub App repository "
                "instead of submitting a repository URL."
            ),
        )
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
