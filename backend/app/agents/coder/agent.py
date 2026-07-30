# Module purpose: Implement agent behavior for the AI agent domain.

import time
from dataclasses import dataclass
from typing import Any, Protocol

from agents import (
    Agent,
    ModelSettings,
    RunConfig,
    Runner,
    function_tool,
)
from pydantic import ValidationError

from app.agents.coder.instructions import (
    CODER_AGENT_NAME,
    CODER_INSTRUCTIONS,
)
from app.agents.configuration import (
    configure_openai_agents,
)
from app.core.config import settings
from app.schemas.changes import CoderOutput
from app.services.changes.editor import (
    RepoPilotPatchEditor,
)
from app.services.planning.agent import (
    extract_usage,
)


# Purpose: Represent coder run result data.
@dataclass(frozen=True)
class CoderRunResult:
    output: CoderOutput
    latency_ms: float | None
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    patch_operations_requested: int
    patch_operations_accepted: int
    patch_operations_rejected: int


# Purpose: Define the interface required from coder runner implementations.
class CoderRunner(Protocol):
    model: str

    # Purpose: Run AI agent for the AI agent workflow.
    async def run(
        self,
        coder_input: str,
        *,
        editor: RepoPilotPatchEditor,
        trace_metadata: dict[str, str],
    ) -> CoderRunResult:
        ...


# Purpose: Create update file tool for the AI agent workflow.
def create_update_file_tool(
    editor: RepoPilotPatchEditor,
):
    @function_tool(
        name_override="update_file",
        description_override=(
            "Replace the full contents of an existing approved repository file."
        ),
    )
    async def update_file(
        path: str,
        content: str,
    ) -> dict:
        """Replace an existing approved file with new UTF-8 text content."""

        return editor.update_file(
            path=path,
            content=content,
        )

    return update_file


# Purpose: Create new file tool for the AI agent workflow.
def create_new_file_tool(
    editor: RepoPilotPatchEditor,
):
    @function_tool(
        name_override="create_file",
        description_override=(
            "Create one explicitly approved new UTF-8 repository file. "
            "The parent directory must already exist."
        ),
    )
    async def create_file(
        path: str,
        content: str,
    ) -> dict:
        """Create an explicitly approved new file with complete contents."""

        return editor.create_file(
            path=path,
            content=content,
        )

    return create_file


# Purpose: Create coder agent for the AI agent workflow.
def create_coder_agent(
    editor: RepoPilotPatchEditor,
) -> Agent:
    return Agent(
        name=CODER_AGENT_NAME,
        instructions=CODER_INSTRUCTIONS,
        model=settings.coder_model,
        model_settings=ModelSettings(
            include_usage=True,
        ),
        tools=[
            create_update_file_tool(
                editor
            ),
            create_new_file_tool(
                editor
            ),
        ],
        handoffs=[],
        output_type=CoderOutput,
    )


# Purpose: Encapsulate agents coder runner behavior for the AI agent domain.
class AgentsCoderRunner:
    model = settings.coder_model

    # Purpose: Run AI agent for the AI agent workflow.
    async def run(
        self,
        coder_input: str,
        *,
        editor: RepoPilotPatchEditor,
        trace_metadata: dict[str, str],
    ) -> CoderRunResult:
        configure_openai_agents()
        agent = create_coder_agent(
            editor
        )
        started_at = time.perf_counter()
        result = await Runner.run(
            agent,
            coder_input,
            max_turns=settings.coder_max_turns,
            run_config=RunConfig(
                workflow_name="RepoPilot Coder",
                trace_include_sensitive_data=(
                    settings.coder_trace_include_sensitive_data
                ),
                trace_metadata=trace_metadata,
            ),
        )
        latency_ms = (
            time.perf_counter() - started_at
        ) * 1000

        try:
            output = result.final_output_as(
                CoderOutput,
                raise_if_incorrect_type=True,
            )
        except (TypeError, ValidationError) as exc:
            raise RuntimeError(
                "Coder did not return valid structured output"
            ) from exc

        (
            input_tokens,
            output_tokens,
            total_tokens,
        ) = extract_usage(result.raw_responses)

        return CoderRunResult(
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
