# Module purpose: Implement service behavior for the AI agent domain.

from app.core.config import settings
from app.db.models.change_set import (
    ChangeSet,
)
from app.db.models.execution_plan import (
    ExecutionPlan,
)
from app.db.models.execution_run import (
    ExecutionRun,
)
from app.services.changes.editor import (
    RepoPilotPatchEditor,
)
from app.services.debugging.failure_classifier import (
    FailureClassification,
)


# Purpose: Build debugger input for the AI agent workflow.
def build_debugger_input(
    *,
    plan: ExecutionPlan,
    change_set: ChangeSet,
    execution_run: ExecutionRun,
    classification: FailureClassification,
    editor: RepoPilotPatchEditor,
    attempt_number: int,
) -> str:
    failed_result = classification.failed_result or {}
    stdout = trim_log(
        str(failed_result.get("stdout") or "")
    )
    stderr = trim_log(
        str(failed_result.get("stderr") or "")
    )
    sections = [
        "Original Issue:",
        (
            f"{plan.repository_owner}/{plan.repository_name}"
            f"#{plan.issue_number}"
        ),
        "",
        "Approved ExecutionPlan:",
        str(plan.plan_json),
        "",
        "Current ChangeSet:",
        f"ID: {change_set.id}",
        f"Summary: {change_set.summary or ''}",
        "Current unified diff:",
        change_set.diff or "",
        "",
        "Failed ExecutionRun:",
        f"ID: {execution_run.id}",
        f"Overall status: {execution_run.status}",
        f"Failure category: {classification.category}",
        f"Command name: {failed_result.get('name')}",
        f"Command type: {failed_result.get('command_type')}",
        f"Exit code: {failed_result.get('exit_code')}",
        "stdout:",
        stdout,
        "stderr:",
        stderr,
        "",
        "Approved writable files:",
        "\n".join(
            sorted(editor.allowed_files)
        ),
        "",
        f"Attempt number: {attempt_number}",
        "",
        "Current approved file contents:",
    ]

    for file_path in sorted(
        editor.allowed_files
    ):
        sections.extend(
            [
                f"File: {file_path}",
                editor.read_file(file_path),
                "",
            ]
        )

    return "\n".join(sections)


# Purpose: Handle trim log for the AI agent workflow.
def trim_log(
    text: str,
) -> str:
    limit = settings.debugger_failure_log_max_chars

    if len(text) <= limit:
        return text

    return text[-limit:]
