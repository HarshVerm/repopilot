from pathlib import Path

from app.db.models.change_set import (
    ChangeSet,
)
from app.services.changes.diff import (
    summarize_diff,
)
from app.services.changes.git import (
    get_base_commit_sha,
    get_git_status,
)


class InvalidChangeSetStateError(ValueError):
    pass


class WorkspaceStateMismatchError(ValueError):
    pass


def validate_change_set_eligibility(
    change_set: ChangeSet,
) -> None:
    if change_set.status != "generated":
        raise InvalidChangeSetStateError(
            "Only generated ChangeSets can be executed"
        )

    if not change_set.base_commit_sha:
        raise WorkspaceStateMismatchError(
            "ChangeSet does not have a base commit SHA"
        )


def validate_workspace_consistency(
    *,
    change_set: ChangeSet,
    repository_path: Path,
) -> None:
    if not repository_path.exists():
        raise WorkspaceStateMismatchError(
            "Workspace repository does not exist"
        )

    current_base = get_base_commit_sha(
        repository_path
    )

    if current_base != change_set.base_commit_sha:
        raise WorkspaceStateMismatchError(
            "Workspace base commit does not match ChangeSet"
        )

    status = get_git_status(
        repository_path
    )

    if any(
        line.startswith("?? ")
        for line in status.splitlines()
    ):
        raise WorkspaceStateMismatchError(
            "Workspace has untracked files"
        )

    diff_summary = summarize_diff(
        repository_path
    )
    recorded_files = {
        file.path: file
        for file in change_set.files
    }
    actual_files = {
        file.path: file
        for file in diff_summary.files
    }

    if set(actual_files) != set(recorded_files):
        raise WorkspaceStateMismatchError(
            "Workspace changed files do not match ChangeSet"
        )

    if diff_summary.diff != change_set.diff:
        raise WorkspaceStateMismatchError(
            "Workspace diff does not match ChangeSet"
        )

    for path, actual in actual_files.items():
        recorded = recorded_files[path]

        if (
            actual.before_sha256
            != recorded.before_sha256
            or actual.after_sha256
            != recorded.after_sha256
            or actual.lines_added
            != recorded.lines_added
            or actual.lines_deleted
            != recorded.lines_deleted
        ):
            raise WorkspaceStateMismatchError(
                "Workspace file metadata does not match ChangeSet"
            )


def safe_container_environment() -> dict[str, str]:
    return {
        "CI": "true",
        "REPOPILOT_SANDBOX": "true",
    }
