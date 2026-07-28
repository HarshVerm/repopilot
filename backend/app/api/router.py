from fastapi import APIRouter

from app.api.routes.github import router as github_router


api_router = APIRouter(
    prefix="/api/v1"
)

api_router.include_router(github_router)