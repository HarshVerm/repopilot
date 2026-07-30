# Module purpose: Implement validator behavior for the change-set domain.

from pathlib import Path

from app.core.config import settings
from app.services.changes.diff import (
    DiffSummary,
)
from app.services.changes.policy import (
    PathPolicyError,
    validate_editable_path,
)


# Purpose: Signal unauthorized file change failures.
class UnauthorizedFileChangeError(ValueError):
    pass


# Purpose: Signal diff limit exceeded failures.
class DiffLimitExceededError(ValueError):
    pass


# Purpose: Validate actual changes for the change-set workflow.
def validate_actual_changes(
    *,
    repository_path: Path,
    allowed_files: set[str],
    diff_summary: DiffSummary,
) -> None:
    changed_paths = {
        file.path
        for file in diff_summary.files
    }

    unauthorized = changed_paths - allowed_files

    if unauthorized:
        raise UnauthorizedFileChangeError(
            "Unauthorized files were modified: "
            + ", ".join(
                sorted(unauthorized)
            )
        )

    for file in diff_summary.files:
        try:
            validate_editable_path(
                repository_path=repository_path,
                requested_path=file.path,
                allowed_files=allowed_files,
            )
        except PathPolicyError as exc:
            raise UnauthorizedFileChangeError(
                str(exc)
            ) from exc

    if len(diff_summary.files) > settings.max_changed_files:
        raise DiffLimitExceededError(
            "Changed-file limit exceeded"
        )

    if (
        diff_summary.lines_added
        + diff_summary.lines_deleted
        > settings.max_total_lines_changed
    ):
        raise DiffLimitExceededError(
            "Total line-change limit exceeded"
        )
