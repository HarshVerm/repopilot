from fastapi import APIRouter

from app.api.routes.github import (
    router as github_router,
)
from app.api.routes.workspaces import (
    router as workspace_router,
)


api_router = APIRouter(
    prefix="/api/v1"
)

api_router.include_router(github_router)

api_router.include_router(
    workspace_router
)