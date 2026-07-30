# Module purpose: Implement git behavior for the change-set domain.

import subprocess
from pathlib import Path

from app.services.indexing.scanner import (
    is_relative_to,
)


# Purpose: Signal dirty workspace failures.
class DirtyWorkspaceError(RuntimeError):
    pass


# Purpose: Signal git command failures.
class GitCommandError(RuntimeError):
    pass


# Purpose: Run git for the change-set workflow.
def run_git(
    repository_path: Path,
    args: list[str],
) -> str:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repository_path),
            *args,
        ],
        capture_output=True,
        check=False,
        text=True,
    )

    if result.returncode != 0:
        raise GitCommandError(
            "Git command failed: "
            + (result.stderr.strip() or result.stdout.strip())
        )

    return result.stdout


# Purpose: Return git status for the change-set workflow.
def get_git_status(
    repository_path: Path,
) -> str:
    return run_git(
        repository_path,
        [
            "status",
            "--porcelain",
        ],
    )


# Purpose: Require clean workspace, raising an error when unavailable.
def require_clean_workspace(
    repository_path: Path,
) -> None:
    status = get_git_status(
        repository_path
    )

    if status.strip():
        raise DirtyWorkspaceError(
            "Workspace has uncommitted changes"
        )


# Purpose: Return base commit sha for the change-set workflow.
def get_base_commit_sha(
    repository_path: Path,
) -> str:
    return run_git(
        repository_path,
        [
            "rev-parse",
            "HEAD",
        ],
    ).strip()


# Purpose: Return tree hash for the change-set workflow.
def get_tree_hash(
    repository_path: Path,
) -> str:
    return run_git(
        repository_path,
        [
            "rev-parse",
            "HEAD^{tree}",
        ],
    ).strip()


# Purpose: Return git diff for the change-set workflow.
def get_git_diff(
    repository_path: Path,
) -> str:
    tracked_diff = run_git(
        repository_path,
        [
            "diff",
            "--no-ext-diff",
            "--unified=3",
        ],
    )
    untracked_diffs = [
        get_untracked_file_diff(
            repository_path,
            file_path,
        )
        for file_path in get_untracked_files(
            repository_path
        )
    ]

    return "\n".join(
        part.rstrip("\n")
        for part in [
            tracked_diff,
            *untracked_diffs,
        ]
        if part
    )


# Purpose: Return untracked files for the change-set workflow.
def get_untracked_files(
    repository_path: Path,
) -> list[str]:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repository_path),
            "ls-files",
            "--others",
            "--exclude-standard",
            "-z",
        ],
        capture_output=True,
        check=False,
    )

    if result.returncode != 0:
        raise GitCommandError(
            "Git command failed: "
            + result.stderr.decode(
                "utf-8",
                errors="replace",
            ).strip()
        )

    return sorted(
        path
        for path in result.stdout.decode(
            "utf-8",
            errors="surrogateescape",
        ).split("\0")
        if path
    )


# Purpose: Return untracked file diff for the change-set workflow.
def get_untracked_file_diff(
    repository_path: Path,
    file_path: str,
) -> str:
    validate_untracked_file_path(
        repository_path,
        file_path,
    )
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repository_path),
            "diff",
            "--no-index",
            "--no-ext-diff",
            "--unified=3",
            "--",
            "/dev/null",
            file_path,
        ],
        capture_output=True,
        check=False,
        text=True,
    )

    if result.returncode not in {
        0,
        1,
    }:
        raise GitCommandError(
            "Git diff failed: "
            + (
                result.stderr.strip()
                or result.stdout.strip()
            )
        )

    return result.stdout


# Purpose: Validate untracked file path for the change-set workflow.
def validate_untracked_file_path(
    repository_path: Path,
    file_path: str,
) -> Path:
    relative_path = Path(file_path)
    if (
        relative_path.is_absolute()
        or ".." in relative_path.parts
        or "\x00" in file_path
    ):
        raise GitCommandError(
            "Unsafe untracked repository path"
        )

    repository_root = repository_path.resolve(
        strict=True
    )
    candidate_path = (
        repository_root / relative_path
    )
    if candidate_path.is_symlink():
        raise GitCommandError(
            "Untracked repository path is a symlink"
        )

    try:
        resolved_path = candidate_path.resolve(
            strict=True
        )
    except OSError as exc:
        raise GitCommandError(
            "Untracked repository path cannot be resolved"
        ) from exc

    if (
        not is_relative_to(
            resolved_path,
            repository_root,
        )
        or not resolved_path.is_file()
    ):
        raise GitCommandError(
            "Untracked repository path escapes workspace"
        )

    return resolved_path


# Purpose: Return changed files for the change-set workflow.
def get_changed_files(
    repository_path: Path,
) -> list[str]:
    output = run_git(
        repository_path,
        [
            "diff",
            "--name-only",
        ],
    )

    return sorted(
        {
            line
            for line in output.splitlines()
            if line
        }
        | set(
            get_untracked_files(
                repository_path
            )
        )
    )


# Purpose: Return numstat for the change-set workflow.
def get_numstat(
    repository_path: Path,
) -> dict[str, tuple[int, int]]:
    output = run_git(
        repository_path,
        [
            "diff",
            "--numstat",
        ],
    )
    stats: dict[str, tuple[int, int]] = {}

    for line in output.splitlines():
        parts = line.split("\t")

        if len(parts) < 3:
            continue

        added_text, deleted_text, path = parts[
            0
        ], parts[1], parts[2]
        added = (
            int(added_text)
            if added_text.isdigit()
            else 0
        )
        deleted = (
            int(deleted_text)
            if deleted_text.isdigit()
            else 0
        )
        stats[path] = (
            added,
            deleted,
        )

    for path in get_untracked_files(
        repository_path
    ):
        content = validate_untracked_file_path(
            repository_path,
            path,
        ).read_bytes()
        stats[path] = (
            len(
                content.decode(
                    "utf-8",
                    errors="ignore",
                ).splitlines()
            ),
            0,
        )

    return stats


# Purpose: Return file at head for the change-set workflow.
def get_file_at_head(
    repository_path: Path,
    file_path: str,
) -> bytes:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repository_path),
            "show",
            f"HEAD:{file_path}",
        ],
        capture_output=True,
        check=False,
    )

    if result.returncode != 0:
        raise GitCommandError(
            "Git file lookup failed"
        )

    return result.stdout
