# Module purpose: Implement integrity behavior for the publication domain.

from pathlib import Path

from app.db.models.change_set import (
    ChangeSet,
)
from app.db.models.execution_plan import (
    ExecutionPlan,
)
from app.db.models.execution_run import (
    ExecutionRun,
)
from app.db.models.final_review import (
    FinalReview,
)
from app.services.changes.policy import (
    is_sensitive_path,
)
from app.services.reviews.service import (
    APPROVED,
    validate_change_set_for_review,
    validate_execution_for_review,
    validate_plan_for_review,
    validate_workspace_relationships,
)


# Purpose: Signal publication failures.
class PublicationError(ValueError):
    pass


# Purpose: Signal review not approved failures.
class ReviewNotApprovedError(PublicationError):
    pass


# Purpose: Signal publication integrity failures.
class PublicationIntegrityError(PublicationError):
    pass


# Purpose: Signal repository mismatch failures.
class RepositoryMismatchError(PublicationIntegrityError):
    pass


# Purpose: Signal branch collision failures.
class BranchCollisionError(PublicationIntegrityError):
    pass


# Purpose: Signal staged file mismatch failures.
class StagedFileMismatchError(PublicationIntegrityError):
    pass


# Purpose: Signal staged diff mismatch failures.
class StagedDiffMismatchError(PublicationIntegrityError):
    pass


# Purpose: Signal commit diff mismatch failures.
class CommitDiffMismatchError(PublicationIntegrityError):
    pass


# Purpose: Signal commit parent mismatch failures.
class CommitParentMismatchError(PublicationIntegrityError):
    pass


# Purpose: Signal publication state failures.
class PublicationStateError(PublicationError):
    pass


# Purpose: Validate publishable review for the publication workflow.
def validate_publishable_review(
    *,
    review: FinalReview,
    plan: ExecutionPlan,
    change_set: ChangeSet,
    execution_run: ExecutionRun,
) -> None:
    if review.status != APPROVED:
        raise ReviewNotApprovedError(
            "Only approved FinalReviews can be published"
        )

    validate_plan_for_review(
        plan
    )
    validate_change_set_for_review(
        change_set
    )
    validate_workspace_relationships(
        plan=plan,
        change_set=change_set,
        execution_run=execution_run,
        review=review,
    )
    validate_execution_for_review(
        change_set=change_set,
        execution_run=execution_run,
    )
    validate_review_repository_snapshot(
        review=review,
        plan=plan,
    )


# Purpose: Validate review repository snapshot for the publication workflow.
def validate_review_repository_snapshot(
    *,
    review: FinalReview,
    plan: ExecutionPlan,
) -> None:
    issue = review.issue_json or {}

    if (
        issue.get("repository_owner")
        != plan.repository_owner
        or issue.get("repository_name")
        != plan.repository_name
        or issue.get("issue_number")
        != plan.issue_number
    ):
        raise RepositoryMismatchError(
            "FinalReview repository snapshot does not match ExecutionPlan"
        )


# Purpose: Handle reviewed file paths for the publication workflow.
def reviewed_file_paths(
    review: FinalReview,
) -> list[str]:
    paths: list[str] = []

    for item in review.files_json or []:
        path = (
            item.get("path")
            if isinstance(
                item,
                dict,
            )
            else None
        )
        if not isinstance(
            path,
            str,
        ):
            raise PublicationIntegrityError(
                "FinalReview file metadata is invalid"
            )

        normalized = validate_reviewed_file_path(
            path
        )
        paths.append(
            normalized
        )

    if not paths:
        raise PublicationIntegrityError(
            "FinalReview does not include reviewed files"
        )

    if len(set(paths)) != len(paths):
        raise PublicationIntegrityError(
            "FinalReview contains duplicate file paths"
        )

    return sorted(
        paths
    )


# Purpose: Validate reviewed file path for the publication workflow.
def validate_reviewed_file_path(
    path: str,
) -> str:
    if "\x00" in path or not path.strip():
        raise PublicationIntegrityError(
            "Reviewed file path is unsafe"
        )

    if any(
        ord(char) < 32
        for char in path
    ):
        raise PublicationIntegrityError(
            "Reviewed file path is unsafe"
        )

    relative_path = Path(path)

    if (
        relative_path.is_absolute()
        or ".." in relative_path.parts
    ):
        raise PublicationIntegrityError(
            "Reviewed file path must be repository-relative"
        )

    normalized = relative_path.as_posix()
    lowered_parts = [
        part.lower()
        for part in relative_path.parts
    ]

    if (
        len(lowered_parts) >= 2
        and lowered_parts[0] == ".github"
        and lowered_parts[1] == "workflows"
    ):
        raise PublicationIntegrityError(
            "Workflow file changes cannot be published in Step 10"
        )

    if is_sensitive_path(
        relative_path
    ):
        raise PublicationIntegrityError(
            "Sensitive file changes cannot be published"
        )

    return normalized


# Purpose: Handle assert hash matches for the publication workflow.
def assert_hash_matches(
    *,
    actual: str,
    expected: str,
    message: str,
    error_type: type[PublicationIntegrityError] = PublicationIntegrityError,
) -> None:
    if actual != expected:
        raise error_type(
            message
        )
