from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    app_name: str = "RepoPilot"
    app_env: str = "development"

    github_token: str | None = None
    openai_api_key: str | None = None

    database_url: str = (
        "postgresql+asyncpg://repopilot:repopilot@localhost:5432/repopilot"
    )
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    embedding_batch_size: int = 32

    planner_model: str = "gpt-5-mini"
    planner_max_turns: int = 4
    planner_trace_include_sensitive_data: bool = False

    coder_model: str = "gpt-5-mini"
    coder_max_turns: int = 8
    coder_trace_include_sensitive_data: bool = False
    max_changed_files: int = 10
    max_total_lines_changed: int = 1000
    max_editable_file_size: int = 2_000_000

    sandbox_root: Path = Path(
        "/tmp/repopilot-sandboxes"
    )
    sandbox_cpu_limit: str = "2"
    sandbox_memory_limit: str = "2g"
    sandbox_pids_limit: int = 256
    sandbox_command_timeout_seconds: int = 600
    sandbox_overall_timeout_seconds: int = 600
    sandbox_stdout_max_bytes: int = 1_000_000
    sandbox_stderr_max_bytes: int = 1_000_000
    sandbox_node_image: str = "node:20-bookworm-slim"
    sandbox_python_image: str = "python:3.11-slim"
    sandbox_container_user: str = "1000:1000"
    sandbox_install_network: str = "bridge"
    sandbox_execution_network: str = "none"

    max_chunk_tokens: int = 1200
    chunk_overlap_tokens: int = 100
    max_context_tokens: int = 6000

    @field_validator("embedding_dimensions")
    @classmethod
    def validate_embedding_dimensions(
        cls,
        value: int,
    ) -> int:
        if value != 1536:
            raise ValueError(
                "The current code_chunks.embedding schema is vector(1536). "
                "Add a migration before changing EMBEDDING_DIMENSIONS."
            )

        return value

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
