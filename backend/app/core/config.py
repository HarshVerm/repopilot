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
