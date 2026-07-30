# Module purpose: Implement configuration behavior for the AI agent domain.

from agents import set_default_openai_key

from app.core.config import settings


# Purpose: Signal agent configuration failures.
class AgentConfigurationError(RuntimeError):
    pass


# Purpose: Handle configure openai agents for the AI agent workflow.
def configure_openai_agents() -> None:
    api_key = (
        settings.openai_api_key or ""
    ).strip()
    if not api_key:
        raise AgentConfigurationError(
            "OPENAI_API_KEY is required for planning, coding, and debugging"
        )

    # Pydantic reads RepoPilot's .env without mutating os.environ. Configure
    # the Agents SDK explicitly so it uses the same validated application key.
    set_default_openai_key(
        api_key,
        use_for_tracing=True,
    )
