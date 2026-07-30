# Module purpose: Implement snapshot behavior for the change-set domain.

import shutil
from pathlib import Path

from app.services.changes.git import (
    get_git_status,
    run_git,
)
from app.services.indexing.scanner import (
    is_relative_to,
)


# Purpose: Parse status paths for the change-set workflow.
def parse_status_paths(
    status_output: str,
) -> list[str]:
    paths: list[str] = []

    for line in status_output.splitlines():
        if len(line) < 4:
            continue

        path_text = line[3:]

        if " -> " in path_text:
            paths.extend(
                part.strip()
                for part in path_text.split(
                    " -> "
                )
            )
        else:
            paths.append(
                path_text.strip()
            )

    return [
        path
        for path in paths
        if path
    ]


# Purpose: Handle safe unlink untracked for the change-set workflow.
def safe_unlink_untracked(
    repository_path: Path,
    path: str,
) -> None:
    relative_path = Path(path)

    if (
        relative_path.is_absolute()
        or ".." in relative_path.parts
        or "\x00" in path
        or not relative_path.parts
    ):
        return

    repo_root = repository_path.resolve()
    candidate = repo_root / relative_path

    try:
        parent = candidate.parent.resolve(
            strict=True
        )
    except OSError:
        return

    if not is_relative_to(
        parent,
        repo_root,
    ):
        return

    if candidate.is_symlink() or candidate.is_file():
        candidate.unlink()
        return

    if candidate.is_dir():
        try:
            resolved_candidate = candidate.resolve(
                strict=True
            )
        except OSError:
            return

        if is_relative_to(
            resolved_candidate,
            repo_root,
        ):
            shutil.rmtree(candidate)


# Purpose: Handle rollback workspace for the change-set workflow.
def rollback_workspace(
    repository_path: Path,
) -> None:
    status = get_git_status(
        repository_path
    )
    paths = parse_status_paths(
        status
    )

    tracked_paths = [
        path
        for path in paths
        if not status_contains_untracked(
            status,
            path,
        )
    ]
    untracked_paths = [
        path
        for path in paths
        if status_contains_untracked(
            status,
            path,
        )
    ]

    if tracked_paths:
        run_git(
            repository_path,
            [
                "checkout",
                "--",
                *tracked_paths,
            ],
        )

    for path in untracked_paths:
        safe_unlink_untracked(
            repository_path,
            path,
        )


# Purpose: Handle status contains untracked for the change-set workflow.
def status_contains_untracked(
    status_output: str,
    path: str,
) -> bool:
    return any(
        line.startswith("?? ")
        and line[3:].strip() == path
        for line in status_output.splitlines()
    )
