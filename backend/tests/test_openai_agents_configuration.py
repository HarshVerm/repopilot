import pytest
from openai import OpenAIError

from app.agents import configuration
from app.agents.configuration import (
    AgentConfigurationError,
    configure_openai_agents,
)
from app.core.config import settings
from app.services.planning.service import (
    planner_failure_message,
)


def test_configure_openai_agents_uses_application_settings(
    monkeypatch,
):
    calls = []
    monkeypatch.setattr(
        settings,
        "openai_api_key",
        "test-openai-key",
    )
    monkeypatch.setattr(
        configuration,
        "set_default_openai_key",
        lambda key, *, use_for_tracing: calls.append(
            (key, use_for_tracing)
        ),
    )

    configure_openai_agents()

    assert calls == [
        (
            "test-openai-key",
            True,
        )
    ]


def test_configure_openai_agents_rejects_missing_key(
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "openai_api_key",
        None,
    )

    with pytest.raises(
        AgentConfigurationError,
        match="OPENAI_API_KEY",
    ):
        configure_openai_agents()


def test_openai_planner_failure_message_is_actionable():
    message = planner_failure_message(
        OpenAIError("provider detail")
    )

    assert "OPENAI_API_KEY" in message
    assert settings.planner_model in message
    assert "provider detail" not in message
