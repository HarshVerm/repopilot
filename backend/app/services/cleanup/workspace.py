import shutil
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.indexing import WORKSPACES_DIR
from app.db.models.task import RepoPilotTask
from app.services.tasks.service import TaskService
from app.services.tasks.state_machine import (
    CANCELLED,
    COMPLETED,
    FAILED,
)


class CleanupSafetyError(ValueError):
    pass


class WorkspaceCleanupService:
    def __init__(
        self,
        *,
        workspaces_root: Path = WORKSPACES_DIR,
        task_service: TaskService | None = None,
    ) -> None:
        self.workspaces_root = (
            workspaces_root.resolve()
        )
        self.task_service = (
            task_service or TaskService()
        )

    async def cleanup_task_workspace(
        self,
        *,
        task: RepoPilotTask,
        db: AsyncSession,
    ) -> dict:
        if task.status not in {
            COMPLETED,
            FAILED,
            CANCELLED,
        }:
            raise CleanupSafetyError(
                "Only completed, failed, or cancelled task workspaces can be cleaned"
            )

        if not task.workspace_id:
            raise CleanupSafetyError(
                "Task has no workspace to clean"
            )

        workspace_path = self.safe_workspace_path(
            task.workspace_id
        )
        existed = workspace_path.exists()

        if existed:
            shutil.rmtree(
                workspace_path
            )

        await self.task_service.record_event(
            task_id=task.id,
            event_type="workspace.cleaned",
            db=db,
            metadata={
                "workspace_id": task.workspace_id,
                "existed": existed,
            },
            commit=True,
        )

        return {
            "workspace_id": task.workspace_id,
            "removed": existed,
        }

    def safe_workspace_path(
        self,
        workspace_id: str,
    ) -> Path:
        if "/" in workspace_id or "\\" in workspace_id:
            raise CleanupSafetyError(
                "Invalid workspace id"
            )

        workspace_path = (
            self.workspaces_root / workspace_id
        ).resolve()

        if not workspace_path.is_relative_to(
            self.workspaces_root
        ):
            raise CleanupSafetyError(
                "Workspace path escapes workspace root"
            )

        if (
            workspace_path.exists()
            and workspace_path.is_symlink()
        ):
            raise CleanupSafetyError(
                "Refusing to clean symlinked workspace"
            )

        return workspace_path
