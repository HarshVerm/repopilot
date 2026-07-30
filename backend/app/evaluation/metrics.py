# Module purpose: Implement metrics behavior for the evaluation domain.

from collections import Counter, defaultdict
from statistics import mean, median
from typing import Any

from app.evaluation.models import (
    EvaluationTaskResultData,
)


# Purpose: Handle aggregate results for the evaluation workflow.
def aggregate_results(
    results: list[EvaluationTaskResultData],
) -> dict[str, Any]:
    total = len(results)
    successful = sum(
        1
        for result in results
        if result.final_success
    )
    first_pass = sum(
        1
        for result in results
        if result.first_patch_passed
    )
    debug_denominator = [
        result
        for result in results
        if result.debug_attempts > 0
    ]
    debug_recovered = sum(
        1
        for result in debug_denominator
        if result.debug_recovered
    )

    return {
        "task_count": total,
        "successful_tasks": successful,
        "success_rate": ratio(
            successful,
            total,
        ),
        "first_pass_successes": first_pass,
        "first_pass_success_rate": ratio(
            first_pass,
            total,
        ),
        "debug_recoveries": debug_recovered,
        "debug_recovery_rate": ratio(
            debug_recovered,
            len(debug_denominator),
        ),
        "average_debug_attempts": (
            mean(
                [
                    result.debug_attempts
                    for result in results
                ]
            )
            if results
            else 0.0
        ),
        "debug_attempt_distribution": dict(
            Counter(
                result.debug_attempts
                for result in results
            )
        ),
        "retrieval": {
            "recall_at_1": average_attr(
                results,
                "retrieval_recall_at_1",
            ),
            "recall_at_3": average_attr(
                results,
                "retrieval_recall_at_3",
            ),
            "recall_at_5": average_attr(
                results,
                "retrieval_recall_at_5",
            ),
            "recall_at_10": average_attr(
                results,
                "retrieval_recall_at_10",
            ),
            "precision_at_5": average_attr(
                results,
                "retrieval_precision_at_5",
            ),
        },
        "planner": {
            "relevant_file_recall": average_attr(
                results,
                "planner_relevant_file_recall",
            ),
            "hallucinated_files": sum(
                result.planner_hallucinated_files
                for result in results
            ),
            "extra_modify_files": sum(
                result.planner_extra_modify_files
                for result in results
            ),
        },
        "verification": {
            "visible_passed": sum(
                result.visible_tests_passed
                for result in results
            ),
            "hidden_passed": sum(
                result.hidden_tests_passed
                for result in results
            ),
        },
        "patch_size": patch_size_metrics(
            results
        ),
        "tokens": token_metrics(
            results
        ),
        "cost": cost_metrics(
            results
        ),
        "latency": latency_metrics(
            results
        ),
        "security": {
            "violations_attempted": sum(
                result.security_violations_attempted
                for result in results
            ),
            "violations_applied": sum(
                result.security_violations_applied
                for result in results
            ),
        },
        "failure_distribution": dict(
            Counter(
                result.failure_category
                or "none"
                for result in results
            )
        ),
        "difficulty_breakdown": breakdown(
            results,
            "difficulty",
        ),
        "category_breakdown": breakdown(
            results,
            "category",
        ),
    }


# Purpose: Handle ratio for the evaluation workflow.
def ratio(
    numerator: int,
    denominator: int,
) -> float:
    if denominator <= 0:
        return 0.0

    return numerator / denominator


# Purpose: Handle average attr for the evaluation workflow.
def average_attr(
    results: list[EvaluationTaskResultData],
    attr: str,
) -> float:
    values = [
        getattr(
            result,
            attr,
        )
        for result in results
        if getattr(
            result,
            attr,
        )
        is not None
    ]

    if not values:
        return 0.0

    return float(
        mean(values)
    )


# Purpose: Handle patch size metrics for the evaluation workflow.
def patch_size_metrics(
    results: list[EvaluationTaskResultData],
) -> dict[str, float | int]:
    totals = [
        result.lines_added
        + result.lines_deleted
        for result in results
    ]

    return {
        "files_changed_total": sum(
            result.files_changed
            for result in results
        ),
        "lines_added_total": sum(
            result.lines_added
            for result in results
        ),
        "lines_deleted_total": sum(
            result.lines_deleted
            for result in results
        ),
        "total_lines_changed_mean": (
            float(mean(totals))
            if totals
            else 0.0
        ),
        "total_lines_changed_median": (
            float(median(totals))
            if totals
            else 0.0
        ),
        "total_lines_changed_p95": p95(
            totals
        ),
    }


# Purpose: Handle token metrics for the evaluation workflow.
def token_metrics(
    results: list[EvaluationTaskResultData],
) -> dict[str, float | int | None]:
    totals = [
        result.total_tokens
        for result in results
    ]
    successful_totals = [
        result.total_tokens
        for result in results
        if result.final_success
    ]

    return {
        "input_tokens": sum(
            result.input_tokens
            for result in results
        ),
        "output_tokens": sum(
            result.output_tokens
            for result in results
        ),
        "total_tokens": sum(totals),
        "median_tokens_per_task": (
            float(median(totals))
            if totals
            else 0.0
        ),
        "tokens_per_successful_task": (
            sum(successful_totals)
            / len(successful_totals)
            if successful_totals
            else None
        ),
    }


# Purpose: Handle cost metrics for the evaluation workflow.
def cost_metrics(
    results: list[EvaluationTaskResultData],
) -> dict[str, float | None]:
    values = [
        result.cost
        for result in results
        if result.cost is not None
    ]

    if not values:
        return {
            "total_cost": None,
            "average_cost_per_task": None,
            "average_cost_per_successful_task": None,
            "median_cost_per_task": None,
        }

    successful = [
        result.cost
        for result in results
        if result.final_success and result.cost is not None
    ]

    return {
        "total_cost": sum(values),
        "average_cost_per_task": sum(values)
        / len(results),
        "average_cost_per_successful_task": (
            sum(successful) / len(successful)
            if successful
            else None
        ),
        "median_cost_per_task": float(
            median(values)
        ),
    }


# Purpose: Handle latency metrics for the evaluation workflow.
def latency_metrics(
    results: list[EvaluationTaskResultData],
) -> dict[str, float]:
    values = [
        result.duration_ms
        for result in results
    ]

    return {
        "mean_ms": (
            float(mean(values))
            if values
            else 0.0
        ),
        "median_ms": (
            float(median(values))
            if values
            else 0.0
        ),
        "p95_ms": p95(values),
    }


# Purpose: Handle breakdown for the evaluation workflow.
def breakdown(
    results: list[EvaluationTaskResultData],
    attr: str,
) -> dict[str, dict[str, int | float]]:
    groups: dict[
        str,
        list[EvaluationTaskResultData],
    ] = defaultdict(list)

    for result in results:
        groups[
            str(
                getattr(
                    result,
                    attr,
                )
            )
        ].append(result)

    return {
        key: {
            "total": len(group),
            "successful": sum(
                result.final_success
                for result in group
            ),
            "success_rate": ratio(
                sum(
                    result.final_success
                    for result in group
                ),
                len(group),
            ),
            "small_sample": len(group) < 5,
        }
        for key, group in sorted(
            groups.items()
        )
    }


# Purpose: Handle p95 for the evaluation workflow.
def p95(
    values: list[int],
) -> float:
    if not values:
        return 0.0

    ordered = sorted(values)
    index = max(
        0,
        min(
            len(ordered) - 1,
            int(
                0.95
                * (len(ordered) - 1)
            ),
        ),
    )
    return float(
        ordered[index]
    )
