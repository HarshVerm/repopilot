# Module purpose: Implement manager behavior for the repository workspace domain.

import asyncio
import shutil
from pathlib import Path
from uuid import uuid4

from app.core.config import settings

from app.services.publishing.authentication import (
    GitHubCredentials,
)
from app.services.publishing.git import (
    credential_env,
    sanitize_error,
)

PROJECT_ROOT = Path(__file__).resolve().parents[4]

WORKSPACES_DIR = settings.workspace_root


# Purpose: Coordinate workspace operations.
class WorkspaceManager:

    # Purpose: Clone repository for the repository workspace workflow.
    async def clone_repository(
        self,
        repository_url: str,
        *,
        workspace_id: str | None = None,
        credentials: GitHubCredentials | None = None,
    ) -> tuple[str, Path]:

        workspace_id = workspace_id or str(uuid4())

        workspace_path = (
            WORKSPACES_DIR
            / workspace_id
        )

        repository_path = (
            workspace_path
            / "repository"
        )

        workspace_path.mkdir(
            parents=True,
            exist_ok=False,
        )

        with credential_env(credentials) as (
            env,
            secrets,
        ):
            process = await asyncio.create_subprocess_exec(
                "git",
                "clone",
                "--depth",
                "1",
                repository_url,
                str(repository_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            _, stderr = await process.communicate()

        if process.returncode != 0:
            shutil.rmtree(
                workspace_path,
                ignore_errors=True,
            )
            raise RuntimeError(
                sanitize_error(
                    stderr.decode(),
                    secrets=secrets,
                )
            )

        return (
            workspace_id,
            repository_path,
        )


workspace_manager = WorkspaceManager()
