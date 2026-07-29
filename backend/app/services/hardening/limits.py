from pathlib import Path
from typing import Any

from app.core.config import Settings, settings


SENSITIVE_PATH_NAMES = {
    ".git",
    ".ssh",
    ".aws",
    ".config",
}


CONFIGURATION_SNAPSHOT_FIELDS = (
    "app_env",
    "database_pool_size",
    "database_max_overflow",
    "database_pool_timeout_seconds",
    "database_pool_recycle_seconds",
    "embedding_model",
    "embedding_dimensions",
    "embedding_batch_size",
    "planner_model",
    "planner_max_turns",
    "coder_model",
    "coder_max_turns",
    "debugger_model",
    "debugger_max_turns",
    "debugger_max_attempts",
    "sandbox_cpu_limit",
    "sandbox_memory_limit",
    "sandbox_pids_limit",
    "sandbox_command_timeout_seconds",
    "sandbox_overall_timeout_seconds",
    "sandbox_stdout_max_bytes",
    "sandbox_stderr_max_bytes",
    "sandbox_install_network",
    "sandbox_execution_network",
    "max_chunk_tokens",
    "chunk_overlap_tokens",
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
    "max_changed_files",
    "max_total_lines_changed",
    "max_editable_file_size",
    "max_task_event_metadata_bytes",
    "openai_timeout_seconds",
    "github_timeout_seconds",
    "github_connect_timeout_seconds",
    "provider_max_retries",
    "provider_retry_initial_backoff_seconds",
    "provider_retry_max_backoff_seconds",
    "rate_limit_window_seconds",
    "rate_limit_task_create",
    "rate_limit_planning",
    "rate_limit_coding",
    "rate_limit_sandbox",
    "rate_limit_debug",
    "rate_limit_publication",
    "rate_limit_evaluation_launch",
    "evaluation_mode",
    "evaluation_suite_name",
    "evaluation_suite_version",
    "evaluation_max_tasks",
    "evaluation_max_concurrency",
    "evaluation_task_timeout_seconds",
    "evaluation_success_rate_gate",
    "evaluation_recall_at_5_gate",
    "evaluation_success_drop_fail_pp",
    "evaluation_recall_drop_fail_pp",
    "evaluation_token_increase_warn_ratio",
    "evaluation_p95_latency_increase_warn_ratio",
    "enable_sensitive_agent_tracing",
)


class StartupConfigurationError(ValueError):
    pass


def configuration_snapshot(
    configured_settings: Settings = settings,
) -> dict[str, Any]:
    return {
        field: _safe_config_value(
            getattr(configured_settings, field)
        )
        for field in CONFIGURATION_SNAPSHOT_FIELDS
    }


def _safe_config_value(
    value: Any,
) -> Any:
    if isinstance(
        value,
        Path,
    ):
        return str(value)

    return value


def validate_startup_configuration(
    configured_settings: Settings = settings,
) -> None:
    validate_safe_root(
        configured_settings.sandbox_root,
        field_name="SANDBOX_ROOT",
    )
    validate_safe_root(
        configured_settings.evaluation_workspaces_root,
        field_name="EVALUATION_WORKSPACES_ROOT",
    )

    if not configured_settings.planner_model.strip():
        raise StartupConfigurationError(
            "PLANNER_MODEL must not be blank"
        )
    if not configured_settings.coder_model.strip():
        raise StartupConfigurationError(
            "CODER_MODEL must not be blank"
        )
    if not configured_settings.debugger_model.strip():
        raise StartupConfigurationError(
            "DEBUGGER_MODEL must not be blank"
        )
    if not configured_settings.embedding_model.strip():
        raise StartupConfigurationError(
            "EMBEDDING_MODEL must not be blank"
        )

    if (
        configured_settings.sandbox_root.resolve()
        == configured_settings.evaluation_workspaces_root.resolve()
    ):
        raise StartupConfigurationError(
            "Sandbox and evaluation workspace roots must be separate"
        )


def validate_safe_root(
    path: Path,
    *,
    field_name: str,
) -> None:
    resolved = path.resolve()

    if resolved == Path("/"):
        raise StartupConfigurationError(
            f"{field_name} cannot be /"
        )

    parts = {
        part.lower()
        for part in resolved.parts
    }

    if parts & SENSITIVE_PATH_NAMES:
        raise StartupConfigurationError(
            f"{field_name} points inside a sensitive directory"
        )


def hardening_checklist() -> list[dict[str, str]]:
    return [
        checklist_item(
            "rate_limiting",
            "implemented",
            "In-process limiter protects expensive API launch operations.",
        ),
        checklist_item(
            "input_bounds",
            "implemented",
            "Centralized limits cover issue, retrieval, repository, patch, sandbox, and event sizes.",
        ),
        checklist_item(
            "provider_timeout",
            "implemented",
            "GitHub/OpenAI clients use bounded timeout configuration.",
        ),
        checklist_item(
            "provider_retry",
            "implemented",
            "Transient provider retry/backoff policy is centralized.",
        ),
        checklist_item(
            "db_pool",
            "implemented",
            "Async SQLAlchemy engine uses configured pool limits and pre-ping.",
        ),
        checklist_item(
            "sandbox_limits",
            "verified",
            "Docker sandbox applies CPU, memory, pids, timeout, output, and network limits.",
        ),
        checklist_item(
            "sensitive_tracing",
            "implemented",
            "Sensitive tracing is disabled by default.",
        ),
        checklist_item(
            "readiness",
            "implemented",
            "Readiness checks database, workspace roots, sandbox root, configuration, and Docker.",
        ),
        checklist_item(
            "secret_redaction",
            "verified",
            "Step 11 redaction is reused for logs/events and tested by regression suite.",
        ),
        checklist_item(
            "workspace_isolation",
            "verified",
            "Path validators and sandbox copy block cross-workspace writes.",
        ),
        checklist_item(
            "publication_integrity",
            "verified",
            "Review status, diff hashes, repository snapshot, branch, and push rules are gated.",
        ),
    ]


def checklist_item(
    control: str,
    status: str,
    details: str,
) -> dict[str, str]:
    return {
        "control": control,
        "status": status,
        "details": details,
    }
