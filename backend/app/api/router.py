from fastapi import APIRouter

from app.api.routes.github import (
    router as github_router,
)

from app.api.routes.workspaces import (
    router as workspace_router,
)

from app.api.routes.indexing import (
    router as indexing_router,
)

from app.api.routes.retrieval import (
    router as retrieval_router,
)

from app.api.routes.plans import (
    router as plans_router,
)

from app.api.routes.coding import (
    router as coding_router,
)


api_router = APIRouter(
    prefix="/api/v1"
)

api_router.include_router(
    github_router
)

api_router.include_router(
    workspace_router
)

api_router.include_router(
    indexing_router
)

api_router.include_router(
    retrieval_router
)

api_router.include_router(
    plans_router
)

api_router.include_router(
    coding_router
)
