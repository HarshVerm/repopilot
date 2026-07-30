# Module purpose: Implement reports behavior for the evaluation domain.

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.evaluation.dataset import (
    REPORTS_ROOT,
    EvaluationSuite,
)
from app.evaluation.metrics import (
    aggregate_results,
)
from app.evaluation.models import (
    EvaluationTaskResultData,
)
from app.services.hardening.limits import (
    hardening_checklist,
)


# Purpose: Build report payload for the evaluation workflow.
def build_report_payload(
    *,
    run_id: str,
    suite: EvaluationSuite,
    status: str,
    configuration: dict[str, Any],
    repopilot_commit_sha: str | None,
    results: list[EvaluationTaskResultData],
    dry_run: bool,
    live_run: bool,
    security_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    aggregate = aggregate_results(
        results
    )
    readiness = production_readiness_report(
        evaluation_run_id=run_id,
        metrics=aggregate,
        security_results=security_results or [],
        live_run=live_run,
    )

    return {
        "run_id": run_id,
        "generated_at": datetime.now(
            UTC
        ).isoformat(),
        "status": status,
        "dry_run": dry_run,
        "live_run": live_run,
        "suite": {
            "name": suite.suite_name,
            "version": suite.suite_version,
            "task_count": len(suite.tasks),
            "difficulty_distribution": (
                suite.difficulty_distribution()
            ),
            "category_distribution": (
                suite.category_distribution()
            ),
        },
        "repopilot_commit_sha": repopilot_commit_sha,
        "configuration": configuration,
        "metrics": aggregate,
        "hardening_checklist": hardening_checklist(),
        "production_readiness": readiness,
        "results": [
            result.model_dump(
                mode="json"
            )
            for result in results
        ],
        "security_results": security_results or [],
    }


# Purpose: Write reports for the evaluation workflow.
def write_reports(
    *,
    run_id: str,
    payload: dict[str, Any],
    output_dir: Path | None = None,
) -> dict[str, str]:
    directory = output_dir or REPORTS_ROOT
    directory.mkdir(
        parents=True,
        exist_ok=True,
    )
    json_path = directory / f"{run_id}.json"
    md_path = directory / f"{run_id}.md"
    json_path.write_text(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    md_path.write_text(
        markdown_report(
            payload
        ),
        encoding="utf-8",
    )

    return {
        "json": str(json_path),
        "markdown": str(md_path),
    }


# Purpose: Handle markdown report for the evaluation workflow.
def markdown_report(
    payload: dict[str, Any],
) -> str:
    metrics = payload["metrics"]
    suite = payload["suite"]
    readiness = payload["production_readiness"]
    lines = [
        f"# RepoPilot Evaluation Report {payload['run_id']}",
        "",
        f"Status: {payload['status']}",
        f"Suite: {suite['name']} {suite['version']}",
        f"Tasks: {suite['task_count']}",
        f"Live benchmark: {'RUN' if payload['live_run'] else 'NOT RUN'}",
        "",
        "## Quality",
        f"Success rate: {percent(metrics['success_rate'])}",
        f"First-pass success: {percent(metrics['first_pass_success_rate'])}",
        f"Debug recovery: {percent(metrics['debug_recovery_rate'])}",
        "",
        "## Retrieval",
        f"Recall@1: {percent(metrics['retrieval']['recall_at_1'])}",
        f"Recall@3: {percent(metrics['retrieval']['recall_at_3'])}",
        f"Recall@5: {percent(metrics['retrieval']['recall_at_5'])}",
        f"Recall@10: {percent(metrics['retrieval']['recall_at_10'])}",
        f"Precision@5: {percent(metrics['retrieval']['precision_at_5'])}",
        "",
        "## Security",
        f"Violations attempted: {metrics['security']['violations_attempted']}",
        f"Violations applied: {metrics['security']['violations_applied']}",
        "",
        "## Production Readiness",
        f"Overall ready: {readiness['overall_ready']}",
    ]

    if readiness["blockers"]:
        lines.append("Blockers:")
        lines.extend(
            f"- {blocker}"
            for blocker in readiness["blockers"]
        )

    if readiness["warnings"]:
        lines.append("Warnings:")
        lines.extend(
            f"- {warning}"
            for warning in readiness["warnings"]
        )

    return "\n".join(lines) + "\n"


# Purpose: Handle production readiness report for the evaluation workflow.
def production_readiness_report(
    *,
    evaluation_run_id: str,
    metrics: dict[str, Any],
    security_results: list[dict[str, Any]],
    live_run: bool,
) -> dict[str, Any]:
    critical_applied = [
        result
        for result in security_results
        if result.get("critical", True)
        and result.get("violation_applied")
    ]
    benchmark_pass = (
        live_run
        and metrics["success_rate"]
        >= settings.evaluation_success_rate_gate
    )
    retrieval_pass = (
        live_run
        and metrics["retrieval"]["recall_at_5"]
        >= settings.evaluation_recall_at_5_gate
    )
    security_pass = not critical_applied
    blockers: list[str] = []
    warnings: list[str] = []

    if critical_applied:
        blockers.append(
            "critical security regression applied"
        )

    if not live_run:
        warnings.append(
            "live benchmark was not executed; quality/retrieval gates are NOT RUN"
        )
    elif not benchmark_pass:
        blockers.append(
            "benchmark success rate is below configured gate"
        )

    if live_run and not retrieval_pass:
        blockers.append(
            "retrieval Recall@5 is below configured gate"
        )

    return {
        "evaluation_run_id": evaluation_run_id,
        "generated_at": datetime.now(
            UTC
        ).isoformat(),
        "security_pass": security_pass,
        "integrity_pass": security_pass,
        "workflow_pass": live_run,
        "benchmark_pass": benchmark_pass,
        "retrieval_pass": retrieval_pass,
        "reliability_pass": live_run,
        "overall_ready": (
            security_pass
            and benchmark_pass
            and retrieval_pass
        ),
        "blockers": blockers,
        "warnings": warnings,
        "metrics": metrics,
    }


# Purpose: Handle percent for the evaluation workflow.
def percent(
    value: float,
) -> str:
    return f"{value * 100:.1f}%"
