# Module purpose: Implement router behavior for the HTTP API domain.

from fastapi import APIRouter

from app.api.routes.github import (
    router as github_router,
)
from app.api.routes.auth import (
    router as auth_router,
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

from app.api.routes.execution import (
    router as execution_router,
)

from app.api.routes.debugging import (
    router as debugging_router,
)

from app.api.routes.reviews import (
    router as reviews_router,
)

from app.api.routes.publishing import (
    router as publishing_router,
)

from app.api.routes.tasks import (
    router as tasks_router,
)

from app.api.routes.readiness import (
    router as readiness_router,
)

from app.api.routes.evaluation import (
    router as evaluation_router,
)


api_router = APIRouter(
    prefix="/api/v1"
)

api_router.include_router(
    auth_router
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

api_router.include_router(
    execution_router
)

api_router.include_router(
    debugging_router
)

api_router.include_router(
    reviews_router
)

api_router.include_router(
    publishing_router
)

api_router.include_router(
    tasks_router
)

api_router.include_router(
    readiness_router
)

api_router.include_router(
    evaluation_router
)
