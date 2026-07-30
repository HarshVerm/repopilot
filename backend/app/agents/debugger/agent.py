# Module purpose: Implement agent behavior for the AI agent domain.

import time
from dataclasses import dataclass
from typing import Protocol

from agents import (
    Agent,
    ModelSettings,
    RunConfig,
    Runner,
)
from pydantic import ValidationError

from app.agents.coder.agent import (
    create_update_file_tool,
)
from app.agents.configuration import (
    configure_openai_agents,
)
from app.agents.debugger.instructions import (
    DEBUGGER_AGENT_NAME,
    DEBUGGER_INSTRUCTIONS,
)
from app.core.config import settings
from app.schemas.debugging import (
    DebuggerOutput,
)
from app.services.changes.editor import (
    RepoPilotPatchEditor,
)
from app.services.planning.agent import (
    extract_usage,
)


# Purpose: Represent debugger run result data.
@dataclass(frozen=True)
class DebuggerRunResult:
    output: DebuggerOutput
    latency_ms: float | None
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    patch_operations_requested: int
    patch_operations_accepted: int
    patch_operations_rejected: int


# Purpose: Define the interface required from debugger runner implementations.
class DebuggerRunner(Protocol):
    model: str

    # Purpose: Run AI agent for the AI agent workflow.
    async def run(
        self,
        debugger_input: str,
        *,
        editor: RepoPilotPatchEditor,
        trace_metadata: dict[str, str],
    ) -> DebuggerRunResult:
        ...


# Purpose: Create debugger agent for the AI agent workflow.
def create_debugger_agent(
    editor: RepoPilotPatchEditor,
) -> Agent:
    return Agent(
        name=DEBUGGER_AGENT_NAME,
        instructions=DEBUGGER_INSTRUCTIONS,
        model=settings.debugger_model,
        model_settings=ModelSettings(
            include_usage=True,
        ),
        tools=[
            create_update_file_tool(
                editor
            )
        ],
        handoffs=[],
        output_type=DebuggerOutput,
    )


# Purpose: Encapsulate agents debugger runner behavior for the AI agent domain.
class AgentsDebuggerRunner:
    model = settings.debugger_model

    # Purpose: Run AI agent for the AI agent workflow.
    async def run(
        self,
        debugger_input: str,
        *,
        editor: RepoPilotPatchEditor,
        trace_metadata: dict[str, str],
    ) -> DebuggerRunResult:
        configure_openai_agents()
        agent = create_debugger_agent(
            editor
        )
        started_at = time.perf_counter()
        result = await Runner.run(
            agent,
            debugger_input,
            max_turns=settings.debugger_max_turns,
            run_config=RunConfig(
                workflow_name="RepoPilot Debugger",
                trace_include_sensitive_data=(
                    settings.debugger_trace_include_sensitive_data
                ),
                trace_metadata=trace_metadata,
            ),
        )
        latency_ms = (
            time.perf_counter() - started_at
        ) * 1000

        try:
            output = result.final_output_as(
                DebuggerOutput,
                raise_if_incorrect_type=True,
            )
        except (TypeError, ValidationError) as exc:
            raise RuntimeError(
                "Debugger did not return valid structured output"
            ) from exc

        (
            input_tokens,
            output_tokens,
            total_tokens,
        ) = extract_usage(result.raw_responses)

        return DebuggerRunResult(
            output=output,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
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
