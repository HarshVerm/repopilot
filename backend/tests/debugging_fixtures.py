import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.debugger.agent import (
    DebuggerRunResult,
)
from app.db.models.execution_run import (
    ExecutionRun,
)
from app.schemas.debugging import (
    DebuggerOutput,
)
from app.services.sandbox.results import (
    DEPENDENCY_INSTALL,
    EXECUTION_FAILED,
    EXECUTION_PASSED,
    EXECUTION_TIMEOUT,
    STATUS_ERROR,
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_TIMEOUT,
    TEST,
    CommandResult,
    ExecutionCommand,
    check_statuses,
)


Scenario = Callable[
    [object, str, dict[str, str]],
    DebuggerOutput,
]


def broken_searchbox_content() -> str:
    return """import { useEffect, useState } from "react";
import { useDebounce } from "../hooks/useDebounce";
import { searchProducts } from "../api/searchApi";

export function SearchBox() {
  const [query, setQuery] = useState("");
  const debouncedQuery = useDebounce(query, 300);

  useEffect(() => {
    searchProducts(debouncedQuery);
  }, [query]);

  return (
    <input
      value={query}
      onChange={(event) => setQuery(event.target.value)}
    />
  );
}
"""


def alternate_searchbox_content() -> str:
    return """import { useEffect, useState } from "react";
import { useDebounce } from "../hooks/useDebounce";
import { searchProducts } from "../api/searchApi";

export function SearchBox() {
  const [query, setQuery] = useState("");
  const debouncedQuery = useDebounce(query, 300);

  useEffect(() => {
    const normalizedQuery = debouncedQuery.trim();

    if (!normalizedQuery) {
      return;
    }

    searchProducts(normalizedQuery);
  }, [debouncedQuery]);

  return (
    <input
      value={query}
      onChange={(event) => setQuery(event.target.value)}
    />
  );
}
"""


def write_broken_searchbox(
    repo: Path,
) -> None:
    (
        repo / "src/components/SearchBox.tsx"
    ).write_text(
        broken_searchbox_content(),
        encoding="utf-8",
    )


class FakeDebuggerRunner:
    model = "fake-debugger-model"

    def __init__(
        self,
        scenarios: list[Scenario],
    ) -> None:
        self.scenarios = scenarios
        self.invocations = 0
        self.inputs: list[str] = []
        self.trace_metadata: list[dict[str, str]] = []

    async def run(
        self,
        debugger_input: str,
        *,
        editor,
        trace_metadata: dict[str, str],
    ) -> DebuggerRunResult:
        self.inputs.append(
            debugger_input
        )
        self.trace_metadata.append(
            trace_metadata
        )
        scenario = self.scenarios[
            self.invocations
        ]
        self.invocations += 1
        output = scenario(
            editor,
            debugger_input,
            trace_metadata,
        )

        return DebuggerRunResult(
            output=output,
            latency_ms=10.0,
            input_tokens=30,
            output_tokens=20,
            total_tokens=50,
            patch_operations_requested=(
                editor.operations_requested
            ),
            patch_operations_accepted=(
                editor.operations_accepted
            ),
            patch_operations_rejected=(
                editor.operations_rejected
            ),
        )


class RaisingDebuggerRunner:
    model = "fake-debugger-model"

    def __init__(
        self,
        exc: Exception,
    ) -> None:
        self.exc = exc
        self.invocations = 0

    async def run(
        self,
        debugger_input: str,
        *,
        editor,
        trace_metadata: dict[str, str],
    ) -> DebuggerRunResult:
        self.invocations += 1
        raise self.exc


class FakeExecutionService:
    def __init__(
        self,
        outcomes: list[dict],
    ) -> None:
        self.outcomes = outcomes
        self.calls: list[uuid.UUID] = []

    async def execute_change_set(
        self,
        *,
        change_set_id: uuid.UUID,
        repository_path: Path,
        db: AsyncSession,
    ) -> ExecutionRun:
        self.calls.append(
            change_set_id
        )
        outcome = self.outcomes.pop(0)

        return await seed_execution_run(
            db=db,
            workspace_id=outcome["workspace_id"],
            change_set_id=change_set_id,
            status=outcome.get(
                "status",
                EXECUTION_FAILED,
            ),
            command_type=outcome.get(
                "command_type",
                TEST,
            ),
            result_status=outcome.get(
                "result_status",
                STATUS_FAIL,
            ),
            stdout=outcome.get(
                "stdout",
                "FAIL SearchBox expected debounced query\n",
            ),
            stderr=outcome.get(
                "stderr",
                "",
            ),
            error_message=outcome.get(
                "error_message"
            ),
        )


async def seed_execution_run(
    *,
    db: AsyncSession,
    workspace_id: str,
    change_set_id: uuid.UUID,
    status: str = EXECUTION_FAILED,
    command_type: str = TEST,
    result_status: str = STATUS_FAIL,
    stdout: str = "FAIL SearchBox expected debounced query\n",
    stderr: str = "",
    error_message: str | None = None,
) -> ExecutionRun:
    command = execution_command(
        command_type
    )
    result = command_result(
        command=command,
        result_status=result_status,
        stdout=stdout,
        stderr=stderr,
    )
    checks = check_statuses(
        [result]
    )
    now = datetime.now(
        UTC
    )

    run = ExecutionRun(
        change_set_id=change_set_id,
        workspace_id=workspace_id,
        status=status,
        started_at=now,
        completed_at=now,
        duration_ms=15.0,
        commands_json=[
            command.to_json()
        ],
        results_json=[
            result.to_json()
        ],
        tests_status=checks["tests"],
        lint_status=checks["lint"],
        typecheck_status=checks["typecheck"],
        build_status=checks["build"],
        timed_out=status == EXECUTION_TIMEOUT
        or result_status == STATUS_TIMEOUT,
        error_message=error_message,
        sandbox_runtime="fake-docker",
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    return run


def execution_command(
    command_type: str,
) -> ExecutionCommand:
    if command_type == DEPENDENCY_INSTALL:
        return ExecutionCommand(
            name="npm install",
            command_type=DEPENDENCY_INSTALL,
            executable="npm",
            args=["install"],
            network_enabled=True,
        )

    return ExecutionCommand(
        name=command_type,
        command_type=command_type,
        executable="npm",
        args=["run", command_type],
    )


def command_result(
    *,
    command: ExecutionCommand,
    result_status: str,
    stdout: str,
    stderr: str,
) -> CommandResult:
    exit_code = 0

    if result_status == STATUS_FAIL:
        exit_code = 1
    elif result_status in {
        STATUS_ERROR,
        STATUS_TIMEOUT,
    }:
        exit_code = None

    return CommandResult(
        name=command.name,
        command_type=command.command_type,
        status=result_status,
        exit_code=exit_code,
        duration_ms=15.0,
        stdout=stdout,
        stderr=stderr,
    )


def passed_outcome(
    workspace_id: str,
) -> dict:
    return {
        "workspace_id": workspace_id,
        "status": EXECUTION_PASSED,
        "result_status": STATUS_PASS,
        "stdout": "PASS SearchBox\n",
    }


def failed_outcome(
    workspace_id: str,
    *,
    stdout: str = "FAIL SearchBox expected debounced query\n",
    command_type: str = TEST,
) -> dict:
    return {
        "workspace_id": workspace_id,
        "status": EXECUTION_FAILED,
        "result_status": STATUS_FAIL,
        "stdout": stdout,
        "command_type": command_type,
    }


def fixed_searchbox_scenario(
    content: str,
) -> Scenario:
    def scenario(
        editor,
        debugger_input: str,
        trace_metadata: dict[str, str],
    ) -> DebuggerOutput:
        editor.update_file(
            path="src/components/SearchBox.tsx",
            content=content,
        )

        return DebuggerOutput(
            diagnosis=(
                "The effect still depends on immediate query updates."
            ),
            failure_category="test_failure",
            likely_root_cause=(
                "The dependency array uses query instead of debouncedQuery."
            ),
            confidence=0.92,
            files_to_modify=[
                "src/components/SearchBox.tsx"
            ],
            repair_steps=[
                "Use debouncedQuery as the effect dependency."
            ],
            retry_recommended=True,
            needs_plan_revision=False,
        )

    return scenario


def plan_revision_scenario(
    editor,
    debugger_input: str,
    trace_metadata: dict[str, str],
) -> DebuggerOutput:
    return DebuggerOutput(
        diagnosis="The debounce hook implementation is insufficient.",
        failure_category="test_failure",
        likely_root_cause=(
            "The observed failure requires changing useDebounce."
        ),
        confidence=0.83,
        files_to_modify=[
            "src/hooks/useDebounce.ts"
        ],
        repair_steps=[
            "Revise the approved plan to include the hook."
        ],
        retry_recommended=False,
        needs_plan_revision=True,
        revision_reason=(
            "The fix requires src/hooks/useDebounce.ts, "
            "which is outside the approved scope."
        ),
    )


def no_change_scenario(
    editor,
    debugger_input: str,
    trace_metadata: dict[str, str],
) -> DebuggerOutput:
    return DebuggerOutput(
        diagnosis="The existing patch already appears to be the repair.",
        failure_category="test_failure",
        likely_root_cause="No source change was identified.",
        confidence=0.55,
        files_to_modify=[
            "src/components/SearchBox.tsx"
        ],
        repair_steps=[],
        retry_recommended=True,
        needs_plan_revision=False,
    )


def update_file_scenario(
    *,
    path: str,
    content: str,
) -> Scenario:
    def scenario(
        editor,
        debugger_input: str,
        trace_metadata: dict[str, str],
    ) -> DebuggerOutput:
        editor.update_file(
            path=path,
            content=content,
        )

        return DebuggerOutput(
            diagnosis="Debugger attempted a policy-protected edit.",
            failure_category="test_failure",
            likely_root_cause="The repair was outside allowed scope.",
            confidence=0.9,
            files_to_modify=[
                path
            ],
            repair_steps=[
                "Apply protected edit."
            ],
            retry_recommended=True,
            needs_plan_revision=False,
        )

    return scenario
