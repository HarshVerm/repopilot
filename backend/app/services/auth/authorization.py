import uuid

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.task import RepoPilotTask
from app.services.auth.service import AuthContext, auth_error
from app.services.tasks.service import TaskService


async def authorize_task(
    *,
    task_id: uuid.UUID | None,
    auth: AuthContext | None,
    db: AsyncSession,
) -> RepoPilotTask | None:
    if task_id is None:
        if (
            auth is None
            and settings.allow_legacy_unauthenticated_api
        ):
            return None
        raise HTTPException(
            status_code=404,
            detail="Task not found",
        )
    if auth is None:
        if not settings.allow_legacy_unauthenticated_api:
            raise auth_error(
                status_code=401,
                code="AUTH_REQUIRED",
                message="Sign in with GitHub to continue.",
            )
        user_id = None
    else:
        user_id = auth.user.id
    task = await TaskService().get_user_task(
        task_id=task_id,
        user_id=user_id,
        db=db,
    )
    if task is None:
        # Deliberately hide cross-tenant existence.
        raise HTTPException(
            status_code=404,
            detail="Task not found",
        )
    return task
