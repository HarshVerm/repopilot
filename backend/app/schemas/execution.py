from pydantic import BaseModel


class CommandResultResponse(BaseModel):
    name: str
    command_type: str
    status: str
    exit_code: int | None
    duration_ms: float
    stdout: str
    stderr: str
    stdout_truncated: bool
    stderr_truncated: bool


class ExecutionRunResponse(BaseModel):
    execution_run_id: str
    change_set_id: str
    workspace_id: str
    status: str
    checks: dict[str, str]
    duration_ms: float | None
    commands: list[dict]
    results: list[CommandResultResponse]
    timed_out: bool
    error_message: str | None = None
