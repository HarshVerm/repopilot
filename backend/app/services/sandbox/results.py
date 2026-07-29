from dataclasses import asdict, dataclass

from app.core.config import settings


STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_SKIPPED = "SKIPPED"
STATUS_TIMEOUT = "TIMEOUT"
STATUS_ERROR = "ERROR"

EXECUTION_PENDING = "pending"
EXECUTION_RUNNING = "running"
EXECUTION_PASSED = "passed"
EXECUTION_FAILED = "failed"
EXECUTION_TIMEOUT = "timeout"
EXECUTION_ERROR = "error"

DEPENDENCY_INSTALL = "dependency_install"
TEST = "test"
TARGETED_TEST = "targeted_test"
TYPECHECK = "typecheck"
LINT = "lint"
BUILD = "build"

VERIFICATION_COMMAND_TYPES = {
    TEST,
    TARGETED_TEST,
    TYPECHECK,
    LINT,
    BUILD,
}


@dataclass(frozen=True)
class ExecutionCommand:
    name: str
    command_type: str
    executable: str
    args: list[str]
    working_directory: str = "."
    timeout_seconds: int = settings.sandbox_command_timeout_seconds
    network_enabled: bool = False
    runtime: str = "node"

    def to_json(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CommandResult:
    name: str
    command_type: str
    status: str
    exit_code: int | None
    duration_ms: float
    stdout: str
    stderr: str
    stdout_truncated: bool = False
    stderr_truncated: bool = False

    def to_json(self) -> dict:
        return asdict(self)


def skipped_result(
    *,
    name: str,
    command_type: str,
    reason: str,
) -> CommandResult:
    return CommandResult(
        name=name,
        command_type=command_type,
        status=STATUS_SKIPPED,
        exit_code=None,
        duration_ms=0.0,
        stdout="",
        stderr=reason,
    )


def truncate_bytes(
    content: bytes | None,
    *,
    limit: int,
) -> tuple[str, bool]:
    if not content:
        return "", False

    truncated = len(content) > limit
    visible = (
        content[-limit:]
        if truncated
        else content
    )

    return (
        visible.decode(
            "utf-8",
            errors="replace",
        ),
        truncated,
    )


def command_result_from_exit(
    *,
    command: ExecutionCommand,
    exit_code: int,
    duration_ms: float,
    stdout: bytes | None,
    stderr: bytes | None,
) -> CommandResult:
    stdout_text, stdout_truncated = truncate_bytes(
        stdout,
        limit=settings.sandbox_stdout_max_bytes,
    )
    stderr_text, stderr_truncated = truncate_bytes(
        stderr,
        limit=settings.sandbox_stderr_max_bytes,
    )

    return CommandResult(
        name=command.name,
        command_type=command.command_type,
        status=(
            STATUS_PASS
            if exit_code == 0
            else STATUS_FAIL
        ),
        exit_code=exit_code,
        duration_ms=duration_ms,
        stdout=stdout_text,
        stderr=stderr_text,
        stdout_truncated=stdout_truncated,
        stderr_truncated=stderr_truncated,
    )


def timeout_result(
    *,
    command: ExecutionCommand,
    duration_ms: float,
    stdout: bytes | None,
    stderr: bytes | None,
) -> CommandResult:
    stdout_text, stdout_truncated = truncate_bytes(
        stdout,
        limit=settings.sandbox_stdout_max_bytes,
    )
    stderr_text, stderr_truncated = truncate_bytes(
        stderr,
        limit=settings.sandbox_stderr_max_bytes,
    )

    return CommandResult(
        name=command.name,
        command_type=command.command_type,
        status=STATUS_TIMEOUT,
        exit_code=None,
        duration_ms=duration_ms,
        stdout=stdout_text,
        stderr=stderr_text,
        stdout_truncated=stdout_truncated,
        stderr_truncated=stderr_truncated,
    )


def error_result(
    *,
    command: ExecutionCommand,
    message: str,
) -> CommandResult:
    return CommandResult(
        name=command.name,
        command_type=command.command_type,
        status=STATUS_ERROR,
        exit_code=None,
        duration_ms=0.0,
        stdout="",
        stderr=message,
    )


def overall_status(
    results: list[CommandResult],
) -> str:
    if any(
        result.status == STATUS_ERROR
        for result in results
    ):
        return EXECUTION_ERROR

    if any(
        result.status == STATUS_TIMEOUT
        for result in results
    ):
        return EXECUTION_TIMEOUT

    if any(
        result.status == STATUS_FAIL
        for result in results
    ):
        return EXECUTION_FAILED

    verification_results = [
        result
        for result in results
        if result.command_type
        in VERIFICATION_COMMAND_TYPES
    ]

    if not any(
        result.status == STATUS_PASS
        for result in verification_results
    ):
        return EXECUTION_ERROR

    return EXECUTION_PASSED


def check_statuses(
    results: list[CommandResult],
) -> dict[str, str]:
    checks = {
        "tests": STATUS_SKIPPED,
        "lint": STATUS_SKIPPED,
        "typecheck": STATUS_SKIPPED,
        "build": STATUS_SKIPPED,
    }

    for result in results:
        if result.command_type in {
            TEST,
            TARGETED_TEST,
        }:
            checks["tests"] = merge_status(
                checks["tests"],
                result.status,
            )
        elif result.command_type == LINT:
            checks["lint"] = merge_status(
                checks["lint"],
                result.status,
            )
        elif result.command_type == TYPECHECK:
            checks["typecheck"] = merge_status(
                checks["typecheck"],
                result.status,
            )
        elif result.command_type == BUILD:
            checks["build"] = merge_status(
                checks["build"],
                result.status,
            )

    return checks


def merge_status(
    current: str,
    incoming: str,
) -> str:
    order = [
        STATUS_SKIPPED,
        STATUS_PASS,
        STATUS_FAIL,
        STATUS_TIMEOUT,
        STATUS_ERROR,
    ]

    return (
        incoming
        if order.index(incoming)
        > order.index(current)
        else current
    )
