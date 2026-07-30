# Module purpose: Implement failures behavior for the task lifecycle domain.

from app.db.models.execution_run import ExecutionRun
from app.services.sandbox.results import (
    BUILD,
    DEPENDENCY_INSTALL,
    EXECUTION_ERROR,
    EXECUTION_FAILED,
    EXECUTION_TIMEOUT,
    LINT,
    STATUS_ERROR,
    STATUS_FAIL,
    STATUS_TIMEOUT,
    TEST,
    TYPECHECK,
)


GITHUB_ERROR = "github_error"
REPOSITORY_CLONE_ERROR = "repository_clone_error"
INDEXING_ERROR = "indexing_error"
RETRIEVAL_ERROR = "retrieval_error"
PLANNER_ERROR = "planner_error"
PLANNER_VALIDATION_ERROR = "planner_validation_error"
CODER_ERROR = "coder_error"
PATCH_POLICY_ERROR = "patch_policy_error"
TEST_FAILURE = "test_failure"
TYPECHECK_FAILURE = "typecheck_failure"
LINT_FAILURE = "lint_failure"
BUILD_FAILURE = "build_failure"
DEPENDENCY_FAILURE = "dependency_failure"
SANDBOX_ERROR = "sandbox_error"
SANDBOX_TIMEOUT = "sandbox_timeout"
DEBUGGER_ERROR = "debugger_error"
DEBUG_ATTEMPTS_EXHAUSTED = "debug_attempts_exhausted"
DEBUG_NO_PROGRESS = "debug_no_progress"
PLAN_REVISION_REQUIRED = "plan_revision_required"
REVIEW_INTEGRITY_ERROR = "review_integrity_error"
REVIEW_REJECTED = "review_rejected"
GIT_ERROR = "git_error"
GITHUB_PUBLISH_ERROR = "github_publish_error"
CONCURRENCY_CONFLICT = "concurrency_conflict"
CANCELLED = "cancelled"
UNKNOWN = "unknown"

FAILURE_CATEGORIES = {
    GITHUB_ERROR,
    REPOSITORY_CLONE_ERROR,
    INDEXING_ERROR,
    RETRIEVAL_ERROR,
    PLANNER_ERROR,
    PLANNER_VALIDATION_ERROR,
    CODER_ERROR,
    PATCH_POLICY_ERROR,
    TEST_FAILURE,
    TYPECHECK_FAILURE,
    LINT_FAILURE,
    BUILD_FAILURE,
    DEPENDENCY_FAILURE,
    SANDBOX_ERROR,
    SANDBOX_TIMEOUT,
    DEBUGGER_ERROR,
    DEBUG_ATTEMPTS_EXHAUSTED,
    DEBUG_NO_PROGRESS,
    PLAN_REVISION_REQUIRED,
    REVIEW_INTEGRITY_ERROR,
    REVIEW_REJECTED,
    GIT_ERROR,
    GITHUB_PUBLISH_ERROR,
    CONCURRENCY_CONFLICT,
    CANCELLED,
    UNKNOWN,
}

RETRYABLE_FAILURES = {
    GITHUB_ERROR,
    REPOSITORY_CLONE_ERROR,
    INDEXING_ERROR,
    RETRIEVAL_ERROR,
    PLANNER_ERROR,
    CODER_ERROR,
    SANDBOX_ERROR,
    SANDBOX_TIMEOUT,
    DEBUGGER_ERROR,
    GIT_ERROR,
    GITHUB_PUBLISH_ERROR,
    CONCURRENCY_CONFLICT,
}


# Purpose: Normalize failure category for the task lifecycle workflow.
def normalize_failure_category(
    category: str | None,
) -> str:
    if category in FAILURE_CATEGORIES:
        return str(category)

    return UNKNOWN


# Purpose: Handle retryable for category for the task lifecycle workflow.
def retryable_for_category(
    category: str | None,
) -> bool:
    return normalize_failure_category(
        category
    ) in RETRYABLE_FAILURES


# Purpose: Classify execution failure for the task lifecycle workflow.
def classify_execution_failure(
    run: ExecutionRun,
) -> str:
    if (
        run.status == EXECUTION_TIMEOUT
        or run.timed_out
    ):
        return SANDBOX_TIMEOUT

    if run.status == EXECUTION_ERROR:
        return SANDBOX_ERROR

    for result in run.results_json or []:
        status = result.get(
            "status"
        )
        command_type = result.get(
            "command_type"
        )

        if status == STATUS_TIMEOUT:
            return SANDBOX_TIMEOUT

        if status == STATUS_ERROR:
            return SANDBOX_ERROR

        if status != STATUS_FAIL:
            continue

        if command_type == DEPENDENCY_INSTALL:
            return DEPENDENCY_FAILURE
        if command_type == TYPECHECK:
            return TYPECHECK_FAILURE
        if command_type == LINT:
            return LINT_FAILURE
        if command_type == BUILD:
            return BUILD_FAILURE
        if command_type == TEST:
            return TEST_FAILURE

    if run.status == EXECUTION_FAILED:
        return TEST_FAILURE

    return UNKNOWN

