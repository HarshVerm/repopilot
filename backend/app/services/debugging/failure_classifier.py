from dataclasses import dataclass

from app.db.models.execution_run import (
    ExecutionRun,
)
from app.services.sandbox.results import (
    BUILD,
    DEPENDENCY_INSTALL,
    LINT,
    STATUS_ERROR,
    STATUS_FAIL,
    STATUS_TIMEOUT,
    TARGETED_TEST,
    TEST,
    TYPECHECK,
)


TEST_FAILURE = "test_failure"
TYPECHECK_FAILURE = "typecheck_failure"
LINT_FAILURE = "lint_failure"
BUILD_FAILURE = "build_failure"
DEPENDENCY_FAILURE = "dependency_failure"
TIMEOUT = "timeout"
SANDBOX_ERROR = "sandbox_error"
INFRASTRUCTURE_ERROR = "infrastructure_error"
NOT_FAILED = "not_failed"
UNKNOWN_FAILURE = "unknown_failure"

ELIGIBLE_FAILURES = {
    TEST_FAILURE,
    TYPECHECK_FAILURE,
    LINT_FAILURE,
    BUILD_FAILURE,
}


@dataclass(frozen=True)
class FailureClassification:
    category: str
    eligible: bool
    reason: str
    failed_result: dict | None


def classify_execution_run(
    execution_run: ExecutionRun,
) -> FailureClassification:
    if execution_run.status in {
        "passed",
        "running",
        "pending",
    }:
        return FailureClassification(
            category=NOT_FAILED,
            eligible=False,
            reason="ExecutionRun is not a failed terminal run",
            failed_result=None,
        )

    results = execution_run.results_json or []

    timeout_result = first_result_with_status(
        results,
        STATUS_TIMEOUT,
    )

    if execution_run.status == "timeout" or timeout_result:
        return FailureClassification(
            category=TIMEOUT,
            eligible=False,
            reason="Timeouts are not auto-debugged in Step 8",
            failed_result=timeout_result,
        )

    error_result = first_result_with_status(
        results,
        STATUS_ERROR,
    )

    if execution_run.status == "error" or error_result:
        return FailureClassification(
            category=classify_error_result(
                execution_run,
                error_result,
            ),
            eligible=False,
            reason="Sandbox or infrastructure errors are not source repairs",
            failed_result=error_result,
        )

    dependency = first_failed_command_type(
        results,
        DEPENDENCY_INSTALL,
    )

    if dependency:
        return FailureClassification(
            category=DEPENDENCY_FAILURE,
            eligible=False,
            reason="Dependency preparation failed",
            failed_result=dependency,
        )

    for command_type, category in [
        (
            TEST,
            TEST_FAILURE,
        ),
        (
            TARGETED_TEST,
            TEST_FAILURE,
        ),
        (
            TYPECHECK,
            TYPECHECK_FAILURE,
        ),
        (
            LINT,
            LINT_FAILURE,
        ),
        (
            BUILD,
            BUILD_FAILURE,
        ),
    ]:
        result = first_failed_command_type(
            results,
            command_type,
        )

        if result:
            return FailureClassification(
                category=category,
                eligible=True,
                reason="Failure may be caused by generated source patch",
                failed_result=result,
            )

    return FailureClassification(
        category=UNKNOWN_FAILURE,
        eligible=False,
        reason="No debuggable failed verification command found",
        failed_result=None,
    )


def first_result_with_status(
    results: list[dict],
    status: str,
) -> dict | None:
    return next(
        (
            result
            for result in results
            if result.get("status") == status
        ),
        None,
    )


def first_failed_command_type(
    results: list[dict],
    command_type: str,
) -> dict | None:
    return next(
        (
            result
            for result in results
            if result.get("command_type") == command_type
            and result.get("status") == STATUS_FAIL
        ),
        None,
    )


def classify_error_result(
    execution_run: ExecutionRun,
    result: dict | None,
) -> str:
    text = " ".join(
        str(value or "")
        for value in [
            execution_run.error_message,
            result.get("stderr")
            if result
            else "",
            result.get("stdout")
            if result
            else "",
        ]
    ).lower()

    if any(
        marker in text
        for marker in [
            "docker",
            "daemon",
            "container",
            "sandboxexecutionerror",
            "not available",
        ]
    ):
        return INFRASTRUCTURE_ERROR

    return SANDBOX_ERROR
