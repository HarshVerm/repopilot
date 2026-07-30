# Module purpose: Implement filesystem behavior for the sandbox execution domain.

import shutil
import uuid
from pathlib import Path

from app.core.config import settings
from app.services.indexing.scanner import (
    is_relative_to,
)


# Purpose: Signal sandbox filesystem failures.
class SandboxFilesystemError(RuntimeError):
    pass


IGNORED_SANDBOX_NAMES = {
    ".git",
    ".env",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".next",
    "dist",
    "build",
    "coverage",
}


# Purpose: Handle sandbox run directory for the sandbox execution workflow.
def sandbox_run_directory(
    execution_run_id: uuid.UUID,
    *,
    sandbox_root: Path = settings.sandbox_root,
) -> Path:
    root = sandbox_root.resolve()
    return root / str(execution_run_id)


# Purpose: Handle sandbox repository directory for the sandbox execution workflow.
def sandbox_repository_directory(
    execution_run_id: uuid.UUID,
    *,
    sandbox_root: Path = settings.sandbox_root,
) -> Path:
    return (
        sandbox_run_directory(
            execution_run_id,
            sandbox_root=sandbox_root,
        )
        / "repository"
    )


# Purpose: Create sandbox copy for the sandbox execution workflow.
def create_sandbox_copy(
    *,
    execution_run_id: uuid.UUID,
    source_repository: Path,
    sandbox_root: Path = settings.sandbox_root,
) -> Path:
    source_root = source_repository.resolve(
        strict=True
    )
    destination_root = sandbox_repository_directory(
        execution_run_id,
        sandbox_root=sandbox_root,
    )
    run_root = destination_root.parent
    safe_root = sandbox_root.resolve()

    if not is_relative_to(
        run_root.resolve(
            strict=False
        ),
        safe_root,
    ):
        raise SandboxFilesystemError(
            "Sandbox path escaped sandbox root"
        )

    run_root.mkdir(
        parents=True,
        exist_ok=False,
    )

    shutil.copytree(
        source_root,
        destination_root,
        symlinks=True,
        ignore=ignore_sandbox_paths,
    )

    return destination_root


# Purpose: Handle ignore sandbox paths for the sandbox execution workflow.
def ignore_sandbox_paths(
    directory: str,
    names: list[str],
) -> set[str]:
    ignored: set[str] = set()

    for name in names:
        if name in IGNORED_SANDBOX_NAMES:
            ignored.add(name)
            continue

        if name.startswith(".env."):
            ignored.add(name)

    return ignored


# Purpose: Clean up sandbox for the sandbox execution workflow.
def cleanup_sandbox(
    run_directory: Path,
    *,
    sandbox_root: Path = settings.sandbox_root,
) -> None:
    safe_root = sandbox_root.resolve()

    try:
        resolved = run_directory.resolve(
            strict=False
        )
    except OSError as exc:
        raise SandboxFilesystemError(
            "Unable to resolve sandbox path"
        ) from exc

    if (
        resolved == safe_root
        or not is_relative_to(
            resolved,
            safe_root,
        )
    ):
        raise SandboxFilesystemError(
            "Refusing to clean outside sandbox root"
        )

    shutil.rmtree(
        resolved,
        ignore_errors=False,
    )
