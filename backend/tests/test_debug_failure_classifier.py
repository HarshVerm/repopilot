import uuid

import pytest

from app.db.models.execution_run import (
    ExecutionRun,
)
from app.services.debugging.failure_classifier import (
    BUILD_FAILURE,
    DEPENDENCY_FAILURE,
    INFRASTRUCTURE_ERROR,
    LINT_FAILURE,
    TEST_FAILURE,
    TIMEOUT,
    TYPECHECK_FAILURE,
    classify_execution_run,
)
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
from tests.debugging_fixtures import (
    command_result,
    execution_command,
)


@pytest.mark.parametrize(
    ("command_type", "expected_category"),
    [
        (
            TEST,
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
    ],
)
def test_code_failures_are_debug_eligible(
    command_type,
    expected_category,
):
    run = execution_run(
        status=EXECUTION_FAILED,
        command_type=command_type,
        result_status=STATUS_FAIL,
    )

    classification = classify_execution_run(
        run
    )

    assert classification.category == expected_category
    assert classification.eligible is True


def test_dependency_failure_is_not_debug_eligible():
    run = execution_run(
        status=EXECUTION_FAILED,
        command_type=DEPENDENCY_INSTALL,
        result_status=STATUS_FAIL,
        stderr="npm registry timeout",
    )

    classification = classify_execution_run(
        run
    )

    assert classification.category == DEPENDENCY_FAILURE
    assert classification.eligible is False


def test_docker_unavailable_is_infrastructure_failure():
    run = execution_run(
        status=EXECUTION_ERROR,
        command_type=TEST,
        result_status=STATUS_ERROR,
        stderr="Docker daemon unavailable",
        error_message="Docker daemon unavailable",
    )

    classification = classify_execution_run(
        run
    )

    assert classification.category == INFRASTRUCTURE_ERROR
    assert classification.eligible is False


def test_timeout_is_not_debug_eligible():
    run = execution_run(
        status=EXECUTION_TIMEOUT,
        command_type=TEST,
        result_status=STATUS_TIMEOUT,
    )

    classification = classify_execution_run(
        run
    )

    assert classification.category == TIMEOUT
    assert classification.eligible is False


def execution_run(
    *,
    status: str,
    command_type: str,
    result_status: str,
    stderr: str = "",
    error_message: str | None = None,
) -> ExecutionRun:
    command = execution_command(
        command_type
    )
    result = command_result(
        command=command,
        result_status=result_status,
        stdout="FAIL expected debounced query",
        stderr=stderr,
    )

    return ExecutionRun(
        id=uuid.uuid4(),
        change_set_id=uuid.uuid4(),
        workspace_id=str(uuid.uuid4()),
        status=status,
        commands_json=[
            command.to_json()
        ],
        results_json=[
            result.to_json()
        ],
        timed_out=status == EXECUTION_TIMEOUT,
        sandbox_runtime="fake-docker",
        error_message=error_message,
    )
