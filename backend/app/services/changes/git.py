import subprocess
from pathlib import Path


class DirtyWorkspaceError(RuntimeError):
    pass


class GitCommandError(RuntimeError):
    pass


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


def get_git_diff(
    repository_path: Path,
) -> str:
    return run_git(
        repository_path,
        [
            "diff",
            "--no-ext-diff",
            "--unified=3",
        ],
    )


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

    return [
        line
        for line in output.splitlines()
        if line
    ]


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

    return stats


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
