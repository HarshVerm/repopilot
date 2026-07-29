from types import SimpleNamespace

from app.evaluation.metrics import (
    aggregate_results,
)
from app.evaluation.models import (
    EvaluationTask,
    EvaluationTaskResultData,
)
from app.evaluation.regression import (
    RegressionThresholds,
    compare_reports,
)
from app.evaluation.reports import (
    production_readiness_report,
)
from app.evaluation.scoring import (
    build_task_result,
    file_level_retrieval_scores,
)
from app.services.sandbox.results import (
    EXECUTION_PASSED,
)


def test_file_level_recall_and_precision_at_5():
    scores = file_level_retrieval_scores(
        relevant_files=[
            "A",
            "B",
        ],
        ranked_results=[
            {"file_path": "A"},
            {"file_path": "C"},
            {"file_path": "D"},
            {"file_path": "B"},
            {"file_path": "E"},
        ],
    )

    assert scores["recall_at_5"] == 1.0
    assert scores["precision_at_5"] == 0.4


def test_first_pass_and_debug_recovery_aggregation():
    results = [
        task_result(
            "task1",
            final_success=True,
            first_patch_passed=True,
        ),
        task_result(
            "task2",
            final_success=True,
            debug_attempts=1,
            debug_recovered=True,
        ),
        task_result(
            "task3",
            final_success=False,
            debug_attempts=1,
        ),
        task_result(
            "task4",
            final_success=True,
            first_patch_passed=True,
        ),
    ]

    aggregate = aggregate_results(
        results
    )

    assert aggregate["success_rate"] == 0.75
    assert aggregate["first_pass_success_rate"] == 0.5
    assert aggregate["debug_recovery_rate"] == 0.5


def test_hidden_test_failure_blocks_final_success():
    task = EvaluationTask(
        id="eval-hidden",
        suite_version="repopilot-eval-v1",
        title="Hidden failure",
        difficulty="easy",
        category="test failure",
        fixture_path="fixtures/polyglot_productivity_app",
        base_commit_sha="a" * 40,
        issue_title="Fix hidden failure",
        issue_body="Visible tests pass but hidden tests fail.",
        relevant_files=["src/app.ts"],
        hidden_test_path="hidden_tests/repopilot-eval-v1/fake.json",
    )
    passed_run = SimpleNamespace(
        status=EXECUTION_PASSED,
        tests_status="pass",
        lint_status="skipped",
        typecheck_status="skipped",
        build_status="skipped",
    )

    result = build_task_result(
        task=task,
        status="passed",
        final_execution_run=passed_run,
        hidden_status="failed",
    )

    assert result.visible_tests_passed is True
    assert result.hidden_tests_passed is False
    assert result.final_success is False


def test_regression_comparison_thresholds():
    baseline = report(
        success=0.80,
        recall5=0.90,
        median_tokens=20_000,
        p95_latency=10_000,
    )
    candidate = report(
        success=0.70,
        recall5=0.82,
        median_tokens=30_000,
        p95_latency=14_000,
    )

    comparison = compare_reports(
        baseline=baseline,
        candidate=candidate,
        thresholds=RegressionThresholds(),
    )

    assert comparison["passed"] is False
    assert "success rate regression exceeds threshold" in comparison[
        "failures"
    ]
    assert "Recall@5 regression exceeds threshold" in comparison[
        "failures"
    ]
    assert comparison["warnings"]


def test_security_applied_violation_fails_readiness():
    readiness = production_readiness_report(
        evaluation_run_id="run",
        metrics=report(
            success=1.0,
            recall5=1.0,
            median_tokens=10,
            p95_latency=10,
        )["metrics"],
        security_results=[
            {
                "critical": True,
                "violation_applied": True,
            }
        ],
        live_run=True,
    )

    assert readiness["security_pass"] is False
    assert readiness["overall_ready"] is False


def task_result(
    task_id: str,
    *,
    final_success: bool,
    first_patch_passed: bool = False,
    debug_attempts: int = 0,
    debug_recovered: bool = False,
) -> EvaluationTaskResultData:
    return EvaluationTaskResultData(
        evaluation_task_id=task_id,
        status=(
            "passed"
            if final_success
            else "failed"
        ),
        difficulty="easy",
        category="test",
        final_success=final_success,
        first_patch_passed=first_patch_passed,
        debug_attempts=debug_attempts,
        debug_recovered=debug_recovered,
    )


def report(
    *,
    success: float,
    recall5: float,
    median_tokens: int,
    p95_latency: int,
) -> dict:
    return {
        "metrics": {
            "success_rate": success,
            "first_pass_success_rate": success,
            "debug_recovery_rate": 0.5,
            "retrieval": {
                "recall_at_5": recall5,
            },
            "tokens": {
                "median_tokens_per_task": median_tokens,
            },
            "latency": {
                "p95_ms": p95_latency,
            },
            "security": {
                "violations_applied": 0,
            },
        }
    }
