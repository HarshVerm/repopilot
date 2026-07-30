# Module purpose: Implement scoring behavior for the evaluation domain.

from pathlib import Path
from typing import Any

from app.evaluation.models import (
    EvaluationTask,
    EvaluationTaskResultData,
    VerificationResults,
)
from app.services.sandbox.results import (
    EXECUTION_PASSED,
    STATUS_ERROR,
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_SKIPPED,
    STATUS_TIMEOUT,
)


RECALL_K_VALUES = (
    1,
    3,
    5,
    10,
)


# Purpose: Handle file level retrieval scores for the evaluation workflow.
def file_level_retrieval_scores(
    *,
    relevant_files: list[str],
    ranked_results: list[dict[str, Any]],
) -> dict[str, float]:
    relevant = {
        normalize_file_path(path)
        for path in relevant_files
    }
    ranked_files = unique_ranked_files(
        ranked_results
    )
    scores: dict[str, float] = {}

    for k in RECALL_K_VALUES:
        scores[f"recall_at_{k}"] = recall_at_k(
            relevant_files=relevant,
            ranked_files=ranked_files,
            k=k,
        )

    scores["precision_at_5"] = precision_at_k(
        relevant_files=relevant,
        ranked_files=ranked_files,
        k=5,
    )
    return scores


# Purpose: Handle unique ranked files for the evaluation workflow.
def unique_ranked_files(
    ranked_results: list[dict[str, Any]],
) -> list[str]:
    seen: set[str] = set()
    ranked_files: list[str] = []

    for result in ranked_results:
        path = normalize_file_path(
            str(
                result.get(
                    "file_path",
                    "",
                )
            )
        )

        if not path or path in seen:
            continue

        seen.add(
            path
        )
        ranked_files.append(
            path
        )

    return ranked_files


# Purpose: Handle recall at k for the evaluation workflow.
def recall_at_k(
    *,
    relevant_files: set[str],
    ranked_files: list[str],
    k: int,
) -> float:
    if not relevant_files:
        return 0.0

    top_k = set(
        ranked_files[:k]
    )
    return len(
        relevant_files & top_k
    ) / len(relevant_files)


# Purpose: Handle precision at k for the evaluation workflow.
def precision_at_k(
    *,
    relevant_files: set[str],
    ranked_files: list[str],
    k: int,
) -> float:
    if k <= 0:
        return 0.0

    top_k = ranked_files[:k]
    return len(
        relevant_files & set(top_k)
    ) / k


# Purpose: Handle planner file metrics for the evaluation workflow.
def planner_file_metrics(
    *,
    task: EvaluationTask,
    plan_json: dict[str, Any] | None,
    fixture_files: set[str],
) -> dict[str, float | int]:
    plan_json = plan_json or {}
    relevant = {
        normalize_file_path(path)
        for path in task.relevant_files
    }
    expected = {
        normalize_file_path(path)
        for path in (
            task.expected_modified_files
            or task.relevant_files
        )
    }
    proposed = {
        normalize_file_path(
            item.get(
                "path",
                "",
            )
        )
        for item in plan_json.get(
            "files_to_modify",
            [],
        )
        if isinstance(
            item,
            dict,
        )
        and item.get("path")
    }
    referenced = proposed | {
        normalize_file_path(
            item.get(
                "path",
                "",
            )
        )
        for item in plan_json.get(
            "files_to_read",
            [],
        )
        if isinstance(
            item,
            dict,
        )
        and item.get("path")
    }

    recall = (
        len(relevant & referenced) / len(relevant)
        if relevant
        else 0.0
    )
    hallucinated = len(
        [
            path
            for path in referenced
            if path not in fixture_files
        ]
    )
    extra_modify = len(
        proposed - expected
    )

    return {
        "planner_relevant_file_recall": recall,
        "planner_hallucinated_files": hallucinated,
        "planner_extra_modify_files": extra_modify,
    }


# Purpose: Handle verification from execution run for the evaluation workflow.
def verification_from_execution_run(
    execution_run,
) -> VerificationResults:
    if execution_run is None:
        return VerificationResults()

    return VerificationResults(
        tests=status_to_verification(
            execution_run.tests_status
        ),
        lint=status_to_verification(
            execution_run.lint_status
        ),
        typecheck=status_to_verification(
            execution_run.typecheck_status
        ),
        build=status_to_verification(
            execution_run.build_status
        ),
    )


# Purpose: Handle status to verification for the evaluation workflow.
def status_to_verification(
    status: str | None,
) -> str:
    if status == STATUS_PASS:
        return "PASS"
    if status == STATUS_FAIL:
        return "FAIL"
    if status == STATUS_TIMEOUT:
        return "TIMEOUT"
    if status == STATUS_ERROR:
        return "ERROR"
    if status == STATUS_SKIPPED or status is None:
        return "SKIPPED"

    return "ERROR"


# Purpose: Build task result for the evaluation workflow.
def build_task_result(
    *,
    task: EvaluationTask,
    status: str,
    retrieval_results: list[dict[str, Any]] | None = None,
    plan_json: dict[str, Any] | None = None,
    fixture_files: set[str] | None = None,
    first_execution_run=None,
    final_execution_run=None,
    hidden_status: str | None = None,
    repo_pilot_task_id: str | None = None,
    debug_attempts: int = 0,
    debug_recovered: bool = False,
    files_changed: int = 0,
    lines_added: int = 0,
    lines_deleted: int = 0,
    input_tokens: int = 0,
    output_tokens: int = 0,
    total_tokens: int = 0,
    cost: float | None = None,
    duration_ms: int = 0,
    failure_category: str | None = None,
    security_violations_attempted: int = 0,
    security_violations_applied: int = 0,
) -> EvaluationTaskResultData:
    retrieval_scores = file_level_retrieval_scores(
        relevant_files=task.relevant_files,
        ranked_results=retrieval_results or [],
    )
    planner_scores = planner_file_metrics(
        task=task,
        plan_json=plan_json,
        fixture_files=fixture_files or set(),
    )
    first_patch_passed = (
        first_execution_run is not None
        and first_execution_run.status == EXECUTION_PASSED
    )
    visible_passed = (
        final_execution_run is not None
        and final_execution_run.status == EXECUTION_PASSED
    )
    hidden_passed = hidden_status in {
        EXECUTION_PASSED,
        STATUS_PASS,
        "passed",
        "PASS",
    }
    final_success = (
        status == "passed"
        and visible_passed
        and hidden_passed
        and security_violations_applied == 0
    )

    return EvaluationTaskResultData(
        evaluation_task_id=task.id,
        status=status,
        difficulty=task.difficulty,
        category=task.category,
        repo_pilot_task_id=repo_pilot_task_id,
        retrieval_recall_at_1=retrieval_scores[
            "recall_at_1"
        ],
        retrieval_recall_at_3=retrieval_scores[
            "recall_at_3"
        ],
        retrieval_recall_at_5=retrieval_scores[
            "recall_at_5"
        ],
        retrieval_recall_at_10=retrieval_scores[
            "recall_at_10"
        ],
        retrieval_precision_at_5=retrieval_scores[
            "precision_at_5"
        ],
        planner_relevant_file_recall=float(
            planner_scores[
                "planner_relevant_file_recall"
            ]
        ),
        planner_hallucinated_files=int(
            planner_scores[
                "planner_hallucinated_files"
            ]
        ),
        planner_extra_modify_files=int(
            planner_scores[
                "planner_extra_modify_files"
            ]
        ),
        first_patch_passed=first_patch_passed,
        debug_attempts=debug_attempts,
        debug_recovered=debug_recovered,
        visible_tests_passed=visible_passed,
        hidden_tests_passed=hidden_passed,
        final_success=final_success,
        verification=verification_from_execution_run(
            final_execution_run
        ),
        files_changed=files_changed,
        lines_added=lines_added,
        lines_deleted=lines_deleted,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cost=cost,
        duration_ms=duration_ms,
        failure_category=failure_category,
        security_violations_attempted=(
            security_violations_attempted
        ),
        security_violations_applied=(
            security_violations_applied
        ),
    )


# Purpose: Normalize file path for the evaluation workflow.
def normalize_file_path(
    path: str,
) -> str:
    return Path(path).as_posix().strip()
