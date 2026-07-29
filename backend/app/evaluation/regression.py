from dataclasses import dataclass
from typing import Any

from app.core.config import settings


@dataclass(frozen=True)
class RegressionThresholds:
    success_drop_fail_pp: float = (
        settings.evaluation_success_drop_fail_pp
    )
    recall_drop_fail_pp: float = (
        settings.evaluation_recall_drop_fail_pp
    )
    median_token_increase_warn_ratio: float = (
        settings.evaluation_token_increase_warn_ratio
    )
    p95_latency_increase_warn_ratio: float = (
        settings.evaluation_p95_latency_increase_warn_ratio
    )


def compare_reports(
    *,
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    thresholds: RegressionThresholds | None = None,
) -> dict[str, Any]:
    active_thresholds = thresholds or RegressionThresholds()
    baseline_metrics = baseline["metrics"]
    candidate_metrics = candidate["metrics"]
    warnings: list[str] = []
    failures: list[str] = []

    success_delta_pp = percentage_point_delta(
        candidate_metrics["success_rate"],
        baseline_metrics["success_rate"],
    )
    first_pass_delta_pp = percentage_point_delta(
        candidate_metrics["first_pass_success_rate"],
        baseline_metrics["first_pass_success_rate"],
    )
    debug_delta_pp = percentage_point_delta(
        candidate_metrics["debug_recovery_rate"],
        baseline_metrics["debug_recovery_rate"],
    )
    recall5_delta_pp = percentage_point_delta(
        candidate_metrics["retrieval"]["recall_at_5"],
        baseline_metrics["retrieval"]["recall_at_5"],
    )
    median_token_delta_ratio = ratio_delta(
        candidate_metrics["tokens"]["median_tokens_per_task"],
        baseline_metrics["tokens"]["median_tokens_per_task"],
    )
    p95_latency_delta_ratio = ratio_delta(
        candidate_metrics["latency"]["p95_ms"],
        baseline_metrics["latency"]["p95_ms"],
    )
    critical_security_failures = candidate_metrics[
        "security"
    ]["violations_applied"]

    if (
        success_delta_pp
        < -active_thresholds.success_drop_fail_pp
    ):
        failures.append(
            "success rate regression exceeds threshold"
        )

    if (
        recall5_delta_pp
        < -active_thresholds.recall_drop_fail_pp
    ):
        failures.append(
            "Recall@5 regression exceeds threshold"
        )

    if critical_security_failures > 0:
        failures.append(
            "critical security violations were applied"
        )

    if (
        median_token_delta_ratio
        > active_thresholds.median_token_increase_warn_ratio
    ):
        warnings.append(
            "median tokens increased beyond warning threshold"
        )

    if (
        p95_latency_delta_ratio
        > active_thresholds.p95_latency_increase_warn_ratio
    ):
        warnings.append(
            "p95 latency increased beyond warning threshold"
        )

    return {
        "deltas": {
            "success_rate_pp": success_delta_pp,
            "first_pass_success_pp": first_pass_delta_pp,
            "debug_recovery_pp": debug_delta_pp,
            "recall_at_5_pp": recall5_delta_pp,
            "median_tokens_ratio": median_token_delta_ratio,
            "p95_latency_ratio": p95_latency_delta_ratio,
            "critical_security_failures": critical_security_failures,
        },
        "warnings": warnings,
        "failures": failures,
        "passed": not failures,
    }


def percentage_point_delta(
    candidate: float,
    baseline: float,
) -> float:
    return (
        candidate - baseline
    ) * 100


def ratio_delta(
    candidate: float | int | None,
    baseline: float | int | None,
) -> float:
    if baseline in {
        None,
        0,
    }:
        return 0.0

    return (
        float(candidate or 0)
        - float(baseline)
    ) / float(baseline)
