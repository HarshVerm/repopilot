from agents import set_default_openai_key

from app.core.config import settings


class AgentConfigurationError(RuntimeError):
    pass


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
