# Module purpose: Define environment-backed application configuration.

from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


# Purpose: Encapsulate settings behavior for the application configuration domain.
class Settings(BaseSettings):
    app_name: str = "RepoPilot"
    app_env: str = "development"
    task_log_level: str = "INFO"

    github_token: str | None = None
    github_app_id: str | None = None
    github_app_private_key: str | None = None
    github_app_private_key_path: Path | None = None
    github_app_client_id: str | None = None
    github_app_client_secret: str | None = None
    github_app_slug: str | None = None
    github_user_token_encryption_secret: str | None = None
    openai_api_key: str | None = None

    app_base_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:3000"
    session_secret: str = "development-only-change-me"
    session_cookie_name: str = "repopilot_session"
    csrf_cookie_name: str = "repopilot_csrf"
    csrf_header_name: str = "X-CSRF-Token"
    cookie_domain: str | None = None
    session_expiry_hours: int = 168
    oauth_state_expiry_minutes: int = 10
    cookie_secure: bool = False
    allow_legacy_unauthenticated_api: bool = True

    database_url: str = (
        "postgresql+asyncpg://repopilot:repopilot@localhost:5432/repopilot"
    )
    database_pool_size: int = 5
    database_max_overflow: int = 5
    database_pool_timeout_seconds: int = 30
    database_pool_recycle_seconds: int = 1800
    database_pool_pre_ping: bool = False

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

    debugger_model: str = "gpt-5-mini"
    debugger_max_turns: int = 6
    debugger_max_attempts: int = 3
    debugger_trace_include_sensitive_data: bool = False
    debugger_failure_log_max_chars: int = 12_000

    sandbox_root: Path = Path(
        "/tmp/repopilot-sandboxes"
    )
    workspace_root: Path = Path(__file__).resolve().parents[3] / "workspaces"
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
    retrieval_top_k_default: int = 10
    retrieval_top_k_max: int = 25
    retrieval_query_max_chars: int = 4000

    max_issue_title_chars: int = 300
    max_issue_body_chars: int = 30_000
    max_repository_files: int = 5000
    max_repository_bytes: int = 250_000_000
    max_indexed_files: int = 2500
    max_code_chunks: int = 20_000
    max_repository_file_size: int = 1_000_000
    max_symbol_count: int = 25_000
    max_task_event_metadata_bytes: int = 32_000

    openai_timeout_seconds: float = 60.0
    github_timeout_seconds: float = 15.0
    github_connect_timeout_seconds: float = 5.0
    http_max_connections: int = 20
    http_max_keepalive_connections: int = 10
    provider_max_retries: int = 3
    provider_retry_initial_backoff_seconds: float = 0.5
    provider_retry_max_backoff_seconds: float = 2.0

    rate_limit_window_seconds: int = 60
    rate_limit_task_create: int = 20
    rate_limit_issue_create: int = 10
    rate_limit_planning: int = 10
    rate_limit_coding: int = 10
    rate_limit_sandbox: int = 12
    rate_limit_debug: int = 8
    rate_limit_publication: int = 5
    rate_limit_evaluation_launch: int = 2

    evaluation_mode: bool = False
    evaluation_suite_name: str = "repopilot-eval"
    evaluation_suite_version: str = "repopilot-eval-v1"
    evaluation_max_tasks: int = 30
    evaluation_max_concurrency: int = 1
    evaluation_task_timeout_seconds: int = 1800
    evaluation_workspaces_root: Path = Path(
        "/tmp/repopilot-evaluation-workspaces"
    )
    evaluation_success_rate_gate: float = 0.70
    evaluation_recall_at_5_gate: float = 0.85
    evaluation_success_drop_fail_pp: float = 5.0
    evaluation_recall_drop_fail_pp: float = 5.0
    evaluation_token_increase_warn_ratio: float = 0.25
    evaluation_p95_latency_increase_warn_ratio: float = 0.30

    enable_sensitive_agent_tracing: bool = False
    readiness_check_timeout_seconds: float = 2.0

    # Purpose: Validate embedding dimensions for the application configuration workflow.
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

    # Purpose: Validate settings for the application configuration workflow.
    @model_validator(mode="after")
    def validate_settings(
        self,
    ) -> "Settings":
        positive_int_fields = (
            "database_pool_size",
            "database_max_overflow",
            "database_pool_timeout_seconds",
            "database_pool_recycle_seconds",
            "embedding_batch_size",
            "planner_max_turns",
            "coder_max_turns",
            "max_changed_files",
            "max_total_lines_changed",
            "max_editable_file_size",
            "debugger_max_turns",
            "debugger_max_attempts",
            "debugger_failure_log_max_chars",
            "sandbox_pids_limit",
            "sandbox_command_timeout_seconds",
            "sandbox_overall_timeout_seconds",
            "sandbox_stdout_max_bytes",
            "sandbox_stderr_max_bytes",
            "max_chunk_tokens",
            "max_context_tokens",
            "retrieval_top_k_default",
            "retrieval_top_k_max",
            "retrieval_query_max_chars",
            "max_issue_title_chars",
            "max_issue_body_chars",
            "max_repository_files",
            "max_repository_bytes",
            "max_indexed_files",
            "max_code_chunks",
            "max_repository_file_size",
            "max_symbol_count",
            "max_task_event_metadata_bytes",
            "http_max_connections",
            "http_max_keepalive_connections",
            "provider_max_retries",
            "rate_limit_window_seconds",
            "rate_limit_task_create",
            "rate_limit_issue_create",
            "rate_limit_planning",
            "rate_limit_coding",
            "rate_limit_sandbox",
            "rate_limit_debug",
            "rate_limit_publication",
            "rate_limit_evaluation_launch",
            "evaluation_max_tasks",
            "evaluation_max_concurrency",
            "evaluation_task_timeout_seconds",
            "session_expiry_hours",
            "oauth_state_expiry_minutes",
        )

        for field_name in positive_int_fields:
            if int(getattr(self, field_name)) <= 0:
                raise ValueError(
                    f"{field_name} must be greater than zero"
                )

        positive_float_fields = (
            "openai_timeout_seconds",
            "github_timeout_seconds",
            "github_connect_timeout_seconds",
            "provider_retry_initial_backoff_seconds",
            "provider_retry_max_backoff_seconds",
            "readiness_check_timeout_seconds",
        )

        for field_name in positive_float_fields:
            if float(getattr(self, field_name)) <= 0:
                raise ValueError(
                    f"{field_name} must be greater than zero"
                )

        if self.retrieval_top_k_default > self.retrieval_top_k_max:
            raise ValueError(
                "retrieval_top_k_default cannot exceed retrieval_top_k_max"
            )

        if self.chunk_overlap_tokens >= self.max_chunk_tokens:
            raise ValueError(
                "chunk_overlap_tokens must be smaller than max_chunk_tokens"
            )

        if self.provider_retry_initial_backoff_seconds > self.provider_retry_max_backoff_seconds:
            raise ValueError(
                "provider retry initial backoff cannot exceed max backoff"
            )

        for field_name in (
            "evaluation_success_rate_gate",
            "evaluation_recall_at_5_gate",
        ):
            value = float(
                getattr(self, field_name)
            )
            if value < 0 or value > 1:
                raise ValueError(
                    f"{field_name} must be between 0 and 1"
                )

        if self.sandbox_install_network in {
            "host",
        } or self.sandbox_install_network.startswith(
            "container:"
        ):
            raise ValueError(
                "sandbox_install_network cannot use host/container network mode"
            )

        if self.sandbox_execution_network in {
            "host",
        } or self.sandbox_execution_network.startswith(
            "container:"
        ):
            raise ValueError(
                "sandbox_execution_network cannot use host/container network mode"
            )

        if self.enable_sensitive_agent_tracing:
            self.planner_trace_include_sensitive_data = True
            self.coder_trace_include_sensitive_data = True
            self.debugger_trace_include_sensitive_data = True

        if self.app_env == "production":
            self.cookie_secure = True
            self.allow_legacy_unauthenticated_api = False
            if (
                self.session_secret
                == "development-only-change-me"
                or len(self.session_secret) < 32
            ):
                raise ValueError(
                    "SESSION_SECRET must be at least 32 characters in production"
                )
            if (
                not self.github_user_token_encryption_secret
                or len(
                    self.github_user_token_encryption_secret
                )
                < 32
            ):
                raise ValueError(
                    "GITHUB_USER_TOKEN_ENCRYPTION_SECRET must be at least "
                    "32 characters in production"
                )
            app_host = urlparse(self.app_base_url).hostname
            frontend_host = urlparse(self.frontend_url).hostname
            if (
                app_host
                and frontend_host
                and app_host != frontend_host
                and not self.cookie_domain
            ):
                raise ValueError(
                    "COOKIE_DOMAIN is required when APP_BASE_URL and "
                    "FRONTEND_URL use different production hosts"
                )

        return self

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )


# Purpose: Return settings for the application configuration workflow.
@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
