import asyncio
from pathlib import Path
from uuid import uuid4


PROJECT_ROOT = Path(__file__).resolve().parents[4]

WORKSPACES_DIR = PROJECT_ROOT / "workspaces"


class WorkspaceManager:

    async def clone_repository(
        self,
        repository_url: str,
    ) -> tuple[str, Path]:

        workspace_id = str(uuid4())

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

        process = await asyncio.create_subprocess_exec(
            "git",
            "clone",
            "--depth",
            "1",
            repository_url,
            str(repository_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise RuntimeError(
                stderr.decode()
            )

        return (
            workspace_id,
            repository_path,
        )


workspace_manager = WorkspaceManager()