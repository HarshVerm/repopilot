# Module purpose: Implement runner behavior for the evaluation domain.

import argparse
import asyncio
import subprocess
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.coder.service import CodingService
from app.core.config import settings
from app.db.models.change_set import ChangeSet
from app.db.models.debug_attempt import DebugAttempt
from app.db.models.evaluation_run import EvaluationRun
from app.db.models.evaluation_task_result import (
    EvaluationTaskResult,
)
from app.db.models.execution_run import ExecutionRun
from app.db.session import AsyncSessionLocal
from app.evaluation.dataset import (
    EvaluationSuite,
    load_evaluation_suite,
    prepare_fixture_workspace,
)
from app.evaluation.evaluator import (
    EvalApprovalPolicy,
    EvaluationContext,
    HiddenTestRunner,
)
from app.evaluation.metrics import (
    aggregate_results,
)
from app.evaluation.models import (
    EvaluationTask,
    EvaluationTaskResultData,
)
from app.evaluation.reports import (
    build_report_payload,
    write_reports,
)
from app.evaluation.scoring import (
    build_task_result,
)
from app.observability.pricing import (
    ModelPricingService,
)
from app.services.debugging.orchestrator import (
    DebugOrchestrator,
)
from app.services.debugging.failure_classifier import (
    classify_execution_run,
)
from app.services.hardening.limits import (
    configuration_snapshot,
)
from app.services.indexing.indexer import (
    index_repository,
)
from app.services.planning.service import (
    PlannerService,
    issue_query_text,
)
from app.services.retrieval.service import (
    build_retrieval_index,
    hybrid_search,
)
from app.services.reviews.service import (
    ReviewService,
)
from app.services.sandbox.manager import (
    ExecutionService,
)
from app.services.sandbox.results import (
    EXECUTION_PASSED,
)
from app.services.tasks.metrics import (
    TaskMetricsService,
)
from app.services.tasks.service import (
    TaskService,
)
from app.services.tasks.state_machine import (
    COMPLETED,
    FAILED,
    INDEXED,
    INDEXING,
)


# Purpose: Signal evaluation run failures.
class EvaluationRunError(RuntimeError):
    pass


# Purpose: Encapsulate evaluation runner behavior for the evaluation domain.
class EvaluationRunner:
    # Purpose: Initialize evaluation runner state and dependencies.
    def __init__(
        self,
        *,
        db_session_factory=AsyncSessionLocal,
        approval_policy: EvalApprovalPolicy | None = None,
        hidden_test_runner: HiddenTestRunner | None = None,
    ) -> None:
        self.db_session_factory = db_session_factory
        self.approval_policy = (
            approval_policy or EvalApprovalPolicy()
        )
        self.hidden_test_runner = (
            hidden_test_runner or HiddenTestRunner()
        )

    # Purpose: Run evaluation for the evaluation workflow.
    async def run(
        self,
        *,
        suite_version: str = settings.evaluation_suite_version,
        task_id: str | None = None,
        difficulty: str | None = None,
        category: str | None = None,
        max_tasks: int | None = None,
        output_dir: Path | None = None,
        dry_run: bool = False,
        live: bool = False,
        mark_baseline: bool = False,
    ) -> dict[str, Any]:
        if live and not settings.evaluation_mode:
            raise EvaluationRunError(
                "Live evaluation requires EVALUATION_MODE=true"
            )

        if max_tasks is not None and max_tasks > settings.evaluation_max_tasks:
            raise EvaluationRunError(
                "max_tasks exceeds EVALUATION_MAX_TASKS"
            )

        suite = load_evaluation_suite(
            suite_version
        )
        selected_suite = suite.filtered(
            task_id=task_id,
            difficulty=difficulty,
            category=category,
            max_tasks=max_tasks,
        )

        if not selected_suite.tasks:
            raise EvaluationRunError(
                "No evaluation tasks matched the requested filters"
            )

        selected_suite.validate(
            require_minimum_tasks=False
        )
        run_id = str(
            uuid.uuid4()
        )
        repopilot_commit_sha = current_git_sha()
        config = configuration_snapshot()

        if dry_run or not live:
            results = dry_run_results(
                selected_suite
            )
            payload = build_report_payload(
                run_id=run_id,
                suite=selected_suite,
                status="completed",
                configuration=config,
                repopilot_commit_sha=repopilot_commit_sha,
                results=results,
                dry_run=True,
                live_run=False,
            )
            paths = write_reports(
                run_id=run_id,
                payload=payload,
                output_dir=output_dir,
            )
            return {
                "run_id": run_id,
                "report": payload,
                "paths": paths,
            }

        async with self.db_session_factory() as db:
            evaluation_run = await self.create_run(
                run_id=run_id,
                suite=selected_suite,
                configuration=config,
                repopilot_commit_sha=repopilot_commit_sha,
                mark_baseline=mark_baseline,
                db=db,
            )

        results: list[EvaluationTaskResultData] = []

        for task in selected_suite.tasks:
            task_started = time.perf_counter()

            async with self.db_session_factory() as db:
                try:
                    result = await asyncio.wait_for(
                        self.run_live_task(
                            suite=selected_suite,
                            task=task,
                            run_id=run_id,
                            db=db,
                        ),
                        timeout=task.timeout_seconds,
                    )
                except TimeoutError:
                    result = EvaluationTaskResultData(
                        evaluation_task_id=task.id,
                        status="timeout",
                        difficulty=task.difficulty,
                        category=task.category,
                        duration_ms=int(
                            (
                                time.perf_counter()
                                - task_started
                            )
                            * 1000
                        ),
                        failure_category="timeout",
                    )
                except Exception as exc:
                    result = EvaluationTaskResultData(
                        evaluation_task_id=task.id,
                        status="error",
                        difficulty=task.difficulty,
                        category=task.category,
                        duration_ms=int(
                            (
                                time.perf_counter()
                                - task_started
                            )
                            * 1000
                        ),
                        failure_category=exc.__class__.__name__,
                    )

                await persist_task_result(
                    evaluation_run_id=evaluation_run.id,
                    result=result,
                    db=db,
                )
                results.append(result)

        payload = build_report_payload(
            run_id=run_id,
            suite=selected_suite,
            status="completed",
            configuration=config,
            repopilot_commit_sha=repopilot_commit_sha,
            results=results,
            dry_run=False,
            live_run=True,
        )
        paths = write_reports(
            run_id=run_id,
            payload=payload,
            output_dir=output_dir,
        )

        async with self.db_session_factory() as db:
            await self.complete_run(
                run_id=run_id,
                results=results,
                report=payload,
                db=db,
            )

        return {
            "run_id": run_id,
            "report": payload,
            "paths": paths,
        }

    # Purpose: Create run for the evaluation workflow.
    async def create_run(
        self,
        *,
        run_id: str,
        suite: EvaluationSuite,
        configuration: dict[str, Any],
        repopilot_commit_sha: str | None,
        mark_baseline: bool,
        db: AsyncSession,
    ) -> EvaluationRun:
        evaluation_run = EvaluationRun(
            id=uuid.UUID(run_id),
            suite_name=suite.suite_name,
            suite_version=suite.suite_version,
            status="running",
            is_baseline=mark_baseline,
            repopilot_commit_sha=repopilot_commit_sha,
            planner_model=settings.planner_model,
            coder_model=settings.coder_model,
            debugger_model=settings.debugger_model,
            embedding_model=settings.embedding_model,
            configuration_json=configuration,
            started_at=datetime.now(UTC),
            total_tasks=len(suite.tasks),
        )
        db.add(
            evaluation_run
        )
        await db.commit()
        await db.refresh(
            evaluation_run
        )
        return evaluation_run

    # Purpose: Run live task for the evaluation workflow.
    async def run_live_task(
        self,
        *,
        suite: EvaluationSuite,
        task: EvaluationTask,
        run_id: str,
        db: AsyncSession,
    ) -> EvaluationTaskResultData:
        started_at = time.perf_counter()
        repository_path = prepare_fixture_workspace(
            suite=suite,
            task=task,
            run_id=run_id,
        )
        workspace_id = (
            f"eval-{run_id[:8]}-{task.id}"
        )[:36]
        issue = {
            "number": issue_number_for_task(task),
            "title": task.issue_title,
            "body": task.issue_body,
        }
        task_service = TaskService()
        repo_task = await task_service.create_task(
            owner="eval",
            repo="polyglot-productivity-app",
            issue_number=issue["number"],
            db=db,
            reuse_active=False,
        )
        await task_service.attach_workspace(
            task_id=repo_task.id,
            workspace_id=workspace_id,
            db=db,
        )
        await task_service.transition_task(
            task_id=repo_task.id,
            new_status=INDEXING,
            db=db,
            event_type="evaluation.indexing_started",
            metadata={
                "evaluation_run_id": run_id,
                "evaluation_task_id": task.id,
            },
        )
        await index_repository(
            workspace_id,
            repository_path,
            db,
        )
        await task_service.transition_task(
            task_id=repo_task.id,
            new_status=INDEXED,
            db=db,
            event_type="evaluation.indexed",
            metadata={
                "evaluation_run_id": run_id,
                "evaluation_task_id": task.id,
            },
        )
        await build_retrieval_index(
            workspace_id=workspace_id,
            repository_path=repository_path,
            db=db,
        )
        retrieval_started = time.perf_counter()
        retrieval_result = await hybrid_search(
            workspace_id=workspace_id,
            query=issue_query_text(issue),
            top_k=settings.retrieval_top_k_default,
            db=db,
            debug=False,
        )
        await task_service.record_event(
            task_id=repo_task.id,
            event_type="retrieval.completed",
            db=db,
            metadata={
                "phase": "evaluation",
                "evaluation_run_id": run_id,
                "evaluation_task_id": task.id,
                "final_result_count": len(
                    retrieval_result.get(
                        "results",
                        [],
                    )
                ),
                "context_token_count": (
                    retrieval_result.get(
                        "context",
                        {},
                    ).get(
                        "estimated_tokens",
                        0,
                    )
                ),
                "latency_ms": (
                    time.perf_counter()
                    - retrieval_started
                )
                * 1000,
            },
            commit=True,
        )
        plan = await PlannerService().create_plan(
            workspace_id=workspace_id,
            repository_path=repository_path,
            owner="eval",
            repo="polyglot-productivity-app",
            issue=issue,
            context_pack=retrieval_result["context"],
            db=db,
            task_id=repo_task.id,
        )
        context = EvaluationContext(
            evaluation_run_id=run_id,
            evaluation_task_id=task.id,
            enabled=True,
        )
        approved_plan = await self.approval_policy.approve_plan(
            plan=plan,
            context=context,
            db=db,
        )
        change_set = await CodingService().implement_plan(
            plan=approved_plan,
            repository_path=repository_path,
            issue=issue,
            context_pack=retrieval_result["context"],
            db=db,
            task_id=repo_task.id,
        )

        first_run = None
        final_run = None
        debug_attempts = 0
        debug_recovered = False
        review = None
        hidden_status = None

        if change_set.status == "generated":
            first_run = await ExecutionService().execute_change_set(
                change_set_id=change_set.id,
                repository_path=repository_path,
                db=db,
                task_id=repo_task.id,
            )
            final_run = first_run

            if (
                first_run.status != EXECUTION_PASSED
                and classify_execution_run(
                    first_run
                ).eligible
            ):
                debug_result = await DebugOrchestrator().debug_execution_run(
                    execution_run_id=first_run.id,
                    repository_path=repository_path,
                    db=db,
                    task_id=repo_task.id,
                )
                debug_attempts = len(
                    debug_result.attempts
                )
                debug_recovered = (
                    debug_result.status == "passed"
                )

                if debug_result.final_execution_run_id:
                    final_run = await db.get(
                        ExecutionRun,
                        debug_result.final_execution_run_id,
                    )

                if debug_result.final_change_set_id:
                    change_set = await db.get(
                        ChangeSet,
                        debug_result.final_change_set_id,
                    )

            if (
                final_run is not None
                and final_run.status == EXECUTION_PASSED
                and change_set is not None
            ):
                review = await ReviewService().create_review(
                    change_set_id=change_set.id,
                    repository_path=repository_path,
                    db=db,
                    task_id=repo_task.id,
                )
                await self.approval_policy.approve_review(
                    review=review,
                    repository_path=repository_path,
                    context=context,
                    db=db,
                )
                hidden_result = self.hidden_test_runner.run(
                    repository_path=repository_path,
                    hidden_test_path=suite.hidden_test_path(
                        task
                    ),
                )
                hidden_status = hidden_result.status

                if hidden_status == EXECUTION_PASSED:
                    await task_service.record_event(
                        task_id=repo_task.id,
                        event_type="evaluation.publication_skipped",
                        db=db,
                        metadata={
                            "evaluation_run_id": run_id,
                            "evaluation_task_id": task.id,
                            "reason": "publication not required for benchmark",
                        },
                        commit=True,
                    )
                    await task_service.transition_task(
                        task_id=repo_task.id,
                        new_status=COMPLETED,
                        db=db,
                        event_type="evaluation.completed",
                        metadata={
                            "evaluation_run_id": run_id,
                            "evaluation_task_id": task.id,
                        },
                        allow_reconcile=True,
                    )
                else:
                    await task_service.transition_task(
                        task_id=repo_task.id,
                        new_status=FAILED,
                        db=db,
                        event_type="evaluation.hidden_tests_failed",
                        failure_category="hidden_test_failure",
                        metadata={
                            "evaluation_run_id": run_id,
                            "evaluation_task_id": task.id,
                            "hidden_status": hidden_status,
                        },
                    )

        metrics = await TaskMetricsService().get_metrics(
            task_id=repo_task.id,
            db=db,
        )
        input_tokens = metrics["agents"]["total"][
            "input_tokens"
        ]
        output_tokens = metrics["agents"]["total"][
            "output_tokens"
        ]
        total_tokens = metrics["agents"]["total"][
            "total_tokens"
        ]
        cost = metrics["agents"]["total"][
            "estimated_cost_usd"
        ]
        result = build_task_result(
            task=task,
            status=(
                "passed"
                if (
                    final_run is not None
                    and final_run.status == EXECUTION_PASSED
                    and hidden_status == EXECUTION_PASSED
                )
                else "failed"
            ),
            retrieval_results=retrieval_result.get(
                "results",
                [],
            ),
            plan_json=plan.plan_json,
            fixture_files=fixture_files(
                repository_path
            ),
            first_execution_run=first_run,
            final_execution_run=final_run,
            hidden_status=hidden_status,
            repo_pilot_task_id=str(
                repo_task.id
            ),
            debug_attempts=debug_attempts,
            debug_recovered=debug_recovered,
            files_changed=change_set.files_changed
            if change_set is not None
            else 0,
            lines_added=change_set.lines_added
            if change_set is not None
            else 0,
            lines_deleted=change_set.lines_deleted
            if change_set is not None
            else 0,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cost=cost,
            duration_ms=int(
                (
                    time.perf_counter()
                    - started_at
                )
                * 1000
            ),
            failure_category=repo_task.failure_category,
        )
        return result

    # Purpose: Handle complete run for the evaluation workflow.
    async def complete_run(
        self,
        *,
        run_id: str,
        results: list[EvaluationTaskResultData],
        report: dict[str, Any],
        db: AsyncSession,
    ) -> None:
        evaluation_run = await db.get(
            EvaluationRun,
            uuid.UUID(run_id),
        )

        if evaluation_run is None:
            raise EvaluationRunError(
                "EvaluationRun not found"
            )

        aggregate = aggregate_results(
            results
        )
        token_metrics = aggregate["tokens"]
        cost_metrics = aggregate["cost"]
        evaluation_run.status = "completed"
        evaluation_run.completed_at = datetime.now(
            UTC
        )
        evaluation_run.total_tasks = len(results)
        evaluation_run.successful_tasks = aggregate[
            "successful_tasks"
        ]
        evaluation_run.first_pass_successes = aggregate[
            "first_pass_successes"
        ]
        evaluation_run.debug_recoveries = aggregate[
            "debug_recoveries"
        ]
        evaluation_run.total_input_tokens = token_metrics[
            "input_tokens"
        ]
        evaluation_run.total_output_tokens = token_metrics[
            "output_tokens"
        ]
        evaluation_run.total_tokens = token_metrics[
            "total_tokens"
        ]
        evaluation_run.total_cost = cost_metrics[
            "total_cost"
        ]
        evaluation_run.total_duration_ms = sum(
            result.duration_ms
            for result in results
        )
        evaluation_run.report_json = report
        await db.commit()


# Purpose: Handle dry run results for the evaluation workflow.
def dry_run_results(
    suite: EvaluationSuite,
) -> list[EvaluationTaskResultData]:
    return [
        EvaluationTaskResultData(
            evaluation_task_id=task.id,
            status="skipped",
            difficulty=task.difficulty,
            category=task.category,
            failure_category="dry_run_not_executed",
        )
        for task in suite.tasks
    ]


# Purpose: Persist task result for the evaluation workflow.
async def persist_task_result(
    *,
    evaluation_run_id: uuid.UUID,
    result: EvaluationTaskResultData,
    db: AsyncSession,
) -> EvaluationTaskResult:
    record = EvaluationTaskResult(
        evaluation_run_id=evaluation_run_id,
        evaluation_task_id=result.evaluation_task_id,
        status=result.status,
        difficulty=result.difficulty,
        category=result.category,
        repo_pilot_task_id=(
            uuid.UUID(result.repo_pilot_task_id)
            if result.repo_pilot_task_id
            else None
        ),
        retrieval_recall_at_1=result.retrieval_recall_at_1,
        retrieval_recall_at_3=result.retrieval_recall_at_3,
        retrieval_recall_at_5=result.retrieval_recall_at_5,
        retrieval_recall_at_10=result.retrieval_recall_at_10,
        retrieval_precision_at_5=result.retrieval_precision_at_5,
        planner_relevant_file_recall=(
            result.planner_relevant_file_recall
        ),
        planner_hallucinated_files=(
            result.planner_hallucinated_files
        ),
        planner_extra_modify_files=(
            result.planner_extra_modify_files
        ),
        first_patch_passed=result.first_patch_passed,
        debug_attempts=result.debug_attempts,
        debug_recovered=result.debug_recovered,
        visible_tests_passed=result.visible_tests_passed,
        hidden_tests_passed=result.hidden_tests_passed,
        final_success=result.final_success,
        files_changed=result.files_changed,
        lines_added=result.lines_added,
        lines_deleted=result.lines_deleted,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        total_tokens=result.total_tokens,
        cost=result.cost,
        duration_ms=result.duration_ms,
        failure_category=result.failure_category,
        security_violations_attempted=(
            result.security_violations_attempted
        ),
        security_violations_applied=(
            result.security_violations_applied
        ),
    )
    db.add(
        record
    )
    await db.commit()
    await db.refresh(
        record
    )
    return record


# Purpose: Load persisted results for the evaluation workflow.
async def load_persisted_results(
    *,
    evaluation_run_id: uuid.UUID,
    db: AsyncSession,
) -> list[EvaluationTaskResultData]:
    rows = list(
        await db.scalars(
            select(EvaluationTaskResult)
            .where(
                EvaluationTaskResult.evaluation_run_id
                == evaluation_run_id
            )
            .order_by(
                EvaluationTaskResult.created_at,
                EvaluationTaskResult.id,
            )
        )
    )

    return [
        EvaluationTaskResultData(
            evaluation_task_id=row.evaluation_task_id,
            status=row.status,
            difficulty=row.difficulty,
            category=row.category,
            repo_pilot_task_id=(
                str(row.repo_pilot_task_id)
                if row.repo_pilot_task_id
                else None
            ),
            retrieval_recall_at_1=row.retrieval_recall_at_1,
            retrieval_recall_at_3=row.retrieval_recall_at_3,
            retrieval_recall_at_5=row.retrieval_recall_at_5,
            retrieval_recall_at_10=row.retrieval_recall_at_10,
            retrieval_precision_at_5=row.retrieval_precision_at_5,
            planner_relevant_file_recall=(
                row.planner_relevant_file_recall
            ),
            planner_hallucinated_files=(
                row.planner_hallucinated_files
            ),
            planner_extra_modify_files=(
                row.planner_extra_modify_files
            ),
            first_patch_passed=row.first_patch_passed,
            debug_attempts=row.debug_attempts,
            debug_recovered=row.debug_recovered,
            visible_tests_passed=row.visible_tests_passed,
            hidden_tests_passed=row.hidden_tests_passed,
            final_success=row.final_success,
            files_changed=row.files_changed,
            lines_added=row.lines_added,
            lines_deleted=row.lines_deleted,
            input_tokens=row.input_tokens,
            output_tokens=row.output_tokens,
            total_tokens=row.total_tokens,
            cost=row.cost,
            duration_ms=row.duration_ms,
            failure_category=row.failure_category,
            security_violations_attempted=(
                row.security_violations_attempted
            ),
            security_violations_applied=(
                row.security_violations_applied
            ),
        )
        for row in rows
    ]


# Purpose: Handle fixture files for the evaluation workflow.
def fixture_files(
    repository_path: Path,
) -> set[str]:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repository_path),
            "ls-files",
        ],
        capture_output=True,
        check=True,
        text=True,
    )
    return {
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip()
    }


# Purpose: Handle current git sha for the evaluation workflow.
def current_git_sha() -> str | None:
    try:
        result = subprocess.run(
            [
                "git",
                "rev-parse",
                "HEAD",
            ],
            capture_output=True,
            check=False,
            text=True,
        )
    except OSError:
        return None

    if result.returncode != 0:
        return None

    return result.stdout.strip()


# Purpose: Issue number for task for the evaluation workflow.
def issue_number_for_task(
    task: EvaluationTask,
) -> int:
    digest = uuid.uuid5(
        uuid.NAMESPACE_URL,
        task.id,
    )
    return int(
        str(digest.int)[:6]
    ) or 1


# Purpose: Build arg parser for the evaluation workflow.
def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run RepoPilot evaluation suites"
    )
    parser.add_argument(
        "--suite",
        default=settings.evaluation_suite_version,
    )
    parser.add_argument(
        "--task",
        default=None,
    )
    parser.add_argument(
        "--difficulty",
        default=None,
    )
    parser.add_argument(
        "--category",
        default=None,
    )
    parser.add_argument(
        "--max-tasks",
        type=int,
        default=None,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
    )
    parser.add_argument(
        "--live",
        action="store_true",
    )
    parser.add_argument(
        "--mark-baseline",
        action="store_true",
    )
    return parser


# Purpose: Handle async main for the evaluation workflow.
async def async_main(
    argv: list[str] | None = None,
) -> dict[str, Any]:
    parser = build_arg_parser()
    args = parser.parse_args(
        argv
    )
    return await EvaluationRunner().run(
        suite_version=args.suite,
        task_id=args.task,
        difficulty=args.difficulty,
        category=args.category,
        max_tasks=args.max_tasks,
        output_dir=args.output,
        dry_run=args.dry_run or not args.live,
        live=args.live,
        mark_baseline=args.mark_baseline,
    )


# Purpose: Handle main for the evaluation workflow.
def main(
    argv: list[str] | None = None,
) -> None:
    result = asyncio.run(
        async_main(argv)
    )
    print(
        result["run_id"]
    )
    print(
        result["paths"]["json"]
    )
    print(
        result["paths"]["markdown"]
    )


if __name__ == "__main__":
    main()
