import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.api.routes.tasks import (
    get_github_client,
)
from app.core.config import settings
from app.db.models.agent_run import AgentRun
from app.db.models.change_set import ChangeSet
from app.db.models.debug_attempt import DebugAttempt
from app.db.models.execution_plan import ExecutionPlan
from app.db.models.execution_run import ExecutionRun
from app.db.models.final_review import FinalReview
from app.db.models.publication import Publication
from app.db.models.task import (
    RepoPilotTask,
)
from app.db.models.task_event import TaskEvent
from app.db.session import (
    AsyncSessionLocal,
    engine,
    get_db,
)
from app.main import app
from app.services.cleanup.workspace import (
    CleanupSafetyError,
    WorkspaceCleanupService,
)
from app.services.tasks.locking import (
    TaskOperationConflict,
    TaskOperationLockService,
)
from app.services.tasks.metrics import (
    TaskMetricsService,
)
from app.services.tasks.reconciler import (
    TaskReconciler,
    detect_stale_task,
)
from app.services.tasks.service import (
    TaskService,
)
from app.services.tasks.state_machine import (
    CANCELLED,
    COMPLETED,
    CREATED,
    DEBUGGING,
    INDEXING,
    PATCH_GENERATED,
    PLAN_APPROVED,
    PLAN_PENDING_APPROVAL,
    PLANNING,
    PUBLISHING,
    REPOSITORY_PREPARING,
    REPOSITORY_READY,
    RETRIEVING,
    REVIEW_APPROVED,
    REVIEW_PENDING,
    TEST_FAILED,
    TESTING,
    TaskConcurrencyError,
    TaskStateMachine,
    TaskTransitionError,
    VERIFICATION_PASSED,
)
from tests.planning_fixtures import (
    valid_planner_output,
)


test_engine = create_async_engine(
    settings.database_url,
    poolclass=NullPool,
)

TestAsyncSessionLocal = async_sessionmaker(
    bind=test_engine,
    expire_on_commit=False,
)


class FakeGitHubClient:
    async def get_repository(
        self,
        owner: str,
        repo: str,
    ) -> dict:
        return {
            "full_name": f"{owner}/{repo}"
        }


async def override_get_db():
    async with TestAsyncSessionLocal() as session:
        yield session


def override_github_client():
    return FakeGitHubClient()


async def dispose_engines() -> None:
    await engine.dispose()
    await test_engine.dispose()


async def cleanup_task_records(
    task_ids: list[uuid.UUID],
) -> None:
    if not task_ids:
        return

    async with AsyncSessionLocal() as db:
        await db.execute(
            delete(Publication).where(
                Publication.task_id.in_(task_ids)
            )
        )
        await db.execute(
            delete(FinalReview).where(
                FinalReview.task_id.in_(task_ids)
            )
        )
        await db.execute(
            delete(DebugAttempt).where(
                DebugAttempt.task_id.in_(task_ids)
            )
        )
        await db.execute(
            delete(ExecutionRun).where(
                ExecutionRun.task_id.in_(task_ids)
            )
        )
        await db.execute(
            delete(ChangeSet).where(
                ChangeSet.task_id.in_(task_ids)
            )
        )
        await db.execute(
            delete(ExecutionPlan).where(
                ExecutionPlan.task_id.in_(task_ids)
            )
        )
        await db.execute(
            delete(RepoPilotTask).where(
                RepoPilotTask.id.in_(task_ids)
            )
        )
        await db.commit()


def test_task_state_machine_rejects_invalid_transitions():
    machine = TaskStateMachine()

    machine.validate_transition(
        current_status=CREATED,
        new_status=REPOSITORY_READY,
    )

    with pytest.raises(TaskTransitionError):
        machine.validate_transition(
            current_status=CREATED,
            new_status=COMPLETED,
        )

    with pytest.raises(TaskTransitionError):
        machine.validate_transition(
            current_status=PLAN_PENDING_APPROVAL,
            new_status=PUBLISHING,
        )

    with pytest.raises(TaskTransitionError):
        machine.validate_transition(
            current_status=VERIFICATION_PASSED,
            new_status=PUBLISHING,
        )


def test_attach_workspace_persists_across_session_refresh():
    created: list[uuid.UUID] = []
    workspace_id = str(uuid.uuid4())

    async def run_test():
        try:
            async with AsyncSessionLocal() as db:
                task = await TaskService().create_task(
                    owner="workspace",
                    repo=f"repo{uuid.uuid4().hex[:8]}",
                    issue_number=1,
                    db=db,
                )
                created.append(task.id)
                attached = await TaskService().attach_workspace(
                    task_id=task.id,
                    workspace_id=workspace_id,
                    db=db,
                )

                assert attached.workspace_id == workspace_id
                assert attached.status == REPOSITORY_READY
                transition_event = (
                    await db.scalars(
                        select(TaskEvent)
                        .where(
                            TaskEvent.task_id == task.id,
                            TaskEvent.event_type
                            == "repository.clone.completed",
                        )
                        .limit(1)
                    )
                ).one()
                assert transition_event.metadata_json[
                    "previous_status"
                ] == REPOSITORY_PREPARING
                assert transition_event.metadata_json[
                    "new_status"
                ] == REPOSITORY_READY
                failed = await TaskService().set_failure(
                    task_id=task.id,
                    db=db,
                    failure_category="unknown",
                    error=RuntimeError(
                        "test failure"
                    ),
                )
                assert failed.status == "failed"
                assert failed.current_step == 2

            async with AsyncSessionLocal() as db:
                persisted = await TaskService().require_task(
                    task_id=created[0],
                    db=db,
                )
                assert persisted.workspace_id == workspace_id
        finally:
            await cleanup_task_records(
                created
            )
            await dispose_engines()

    asyncio.run(run_test())


def test_task_service_concurrency_locks_redaction_and_metrics():
    created: list[uuid.UUID] = []

    async def run_test():
        try:
            async with AsyncSessionLocal() as db:
                service = TaskService()
                task = await service.create_task(
                    owner="tasksuite",
                    repo=f"repo{uuid.uuid4().hex[:8]}",
                    issue_number=101,
                    db=db,
                )
                created.append(task.id)
                task_id = task.id
                other_task = await service.create_task(
                    owner="tasksuite",
                    repo=f"repo{uuid.uuid4().hex[:8]}",
                    issue_number=102,
                    db=db,
                )
                created.append(other_task.id)
                other_task_id = other_task.id
                first_version = task.version

                await service.transition_task(
                    task_id=task_id,
                    new_status=REPOSITORY_READY,
                    db=db,
                    expected_version=first_version,
                )

                with pytest.raises(
                    TaskConcurrencyError
                ):
                    await service.transition_task(
                        task_id=task_id,
                        new_status=INDEXING,
                        db=db,
                        expected_version=first_version,
                )

                await service.record_event(
                    task_id=task_id,
                    event_type="secret.test",
                    db=db,
                    metadata={
                        "Authorization": "Bearer ghp_supersecret1234567890",
                        "OPENAI_API_KEY": "sk-supersecret1234567890",
                        "nested": {
                            "access_token": "token-value"
                        },
                    },
                    message="Bearer sk-message-secret1234567890",
                )
                event = (
                    await db.scalars(
                        select(TaskEvent)
                        .where(
                            TaskEvent.task_id
                            == task_id,
                            TaskEvent.event_type
                            == "secret.test",
                        )
                        .limit(1)
                    )
                ).one()
                assert "supersecret" not in str(
                    event.metadata_json
                )
                assert "message-secret" not in (
                    event.message or ""
                )

                lock_service = TaskOperationLockService()
                await lock_service.acquire(
                    task_id=task_id,
                    operation="coding",
                    db=db,
                )
                await lock_service.acquire(
                    task_id=other_task_id,
                    operation="coding",
                    db=db,
                )
                await lock_service.release(
                    task_id=other_task_id,
                    operation=None,
                    db=db,
                )
                with pytest.raises(
                    TaskOperationConflict
                ):
                    await lock_service.acquire(
                        task_id=task_id,
                        operation="testing",
                        db=db,
                    )
                await lock_service.release(
                    task_id=task_id,
                    operation=None,
                    db=db,
                )

                now = datetime.now(UTC)
                db.add_all(
                    [
                        AgentRun(
                            task_id=task_id,
                            agent_type="planner",
                            model="fake-planner",
                            status="completed",
                            started_at=now,
                            completed_at=now,
                            latency_ms=10.0,
                            input_tokens=100,
                            output_tokens=20,
                            total_tokens=120,
                        ),
                        AgentRun(
                            task_id=task_id,
                            agent_type="coder",
                            model="fake-coder",
                            status="completed",
                            started_at=now,
                            completed_at=now,
                            latency_ms=20.0,
                            input_tokens=200,
                            output_tokens=50,
                            total_tokens=250,
                        ),
                        AgentRun(
                            task_id=task_id,
                            agent_type="debugger",
                            model="fake-debugger",
                            status="completed",
                            started_at=now,
                            completed_at=now,
                            latency_ms=30.0,
                            input_tokens=80,
                            output_tokens=20,
                            total_tokens=100,
                        ),
                    ]
                )
                await db.commit()

                metrics = await TaskMetricsService().get_metrics(
                    task_id=task_id,
                    db=db,
                )
                assert metrics["agents"]["total"][
                    "input_tokens"
                ] == 380
                assert metrics["agents"]["total"][
                    "output_tokens"
                ] == 90
                assert metrics["agents"]["total"][
                    "total_tokens"
                ] == 470

                task.status = "coding"
                task.last_event_at = datetime.now(
                    UTC
                ) - timedelta(
                    hours=2
                )
                stale = detect_stale_task(
                    task,
                    now=datetime.now(UTC),
                )
                assert stale is not None
                assert stale["status"] == "coding"
        finally:
            await cleanup_task_records(
                created
            )
            await dispose_engines()

    asyncio.run(run_test())


def test_task_debug_path_transitions_from_failed_test_to_verified():
    created: list[uuid.UUID] = []

    async def run_test():
        try:
            async with AsyncSessionLocal() as db:
                service = TaskService()
                task = await service.create_task(
                    owner="debugpath",
                    repo=f"repo{uuid.uuid4().hex[:8]}",
                    issue_number=606,
                    db=db,
                )
                created.append(task.id)

                for status, event_type in [
                    (
                        REPOSITORY_READY,
                        "repository.ready",
                    ),
                    (
                        RETRIEVING,
                        "retrieval.started",
                    ),
                    (
                        PLANNING,
                        "planning.started",
                    ),
                    (
                        PLAN_PENDING_APPROVAL,
                        "plan.pending_approval",
                    ),
                    (
                        PLAN_APPROVED,
                        "plan.approved",
                    ),
                    (
                        "coding",
                        "coding.started",
                    ),
                    (
                        PATCH_GENERATED,
                        "patch.generated",
                    ),
                    (
                        TESTING,
                        "sandbox.started",
                    ),
                    (
                        TEST_FAILED,
                        "sandbox.failed",
                    ),
                    (
                        DEBUGGING,
                        "debugger.started",
                    ),
                    (
                        VERIFICATION_PASSED,
                        "debugger.passed",
                    ),
                ]:
                    task = await service.transition_task(
                        task_id=task.id,
                        new_status=status,
                        db=db,
                        event_type=event_type,
                    )

                assert task.status == VERIFICATION_PASSED
                events = list(
                    await db.scalars(
                        select(TaskEvent)
                        .where(
                            TaskEvent.task_id
                            == task.id
                        )
                        .order_by(
                            TaskEvent.created_at
                        )
                    )
                )
                assert [
                    event.event_type
                    for event in events
                ][-2:] == [
                    "debugger.started",
                    "debugger.passed",
                ]
        finally:
            await cleanup_task_records(
                created
            )
            await dispose_engines()

    asyncio.run(run_test())


def test_task_reconciler_cancellation_and_cleanup(tmp_path):
    created: list[uuid.UUID] = []

    async def run_test():
        try:
            async with AsyncSessionLocal() as db:
                service = TaskService()
                task = await service.create_task(
                    owner="reconcile",
                    repo=f"repo{uuid.uuid4().hex[:8]}",
                    issue_number=202,
                    db=db,
                )
                created.append(task.id)
                task_id = task.id
                output = valid_planner_output()
                plan = ExecutionPlan(
                    workspace_id=str(
                        uuid.uuid4()
                    ),
                    task_id=task_id,
                    repository_owner="reconcile",
                    repository_name="repo",
                    issue_number=202,
                    status="pending_approval",
                    summary=output.summary,
                    problem_analysis=(
                        output.problem_analysis
                    ),
                    likely_root_cause=(
                        output.likely_root_cause
                    ),
                    confidence=output.confidence,
                    plan_json=output.model_dump(
                        mode="json"
                    ),
                )
                db.add(plan)
                await db.commit()
                await db.refresh(plan)

                task = await TaskReconciler().reconcile_task(
                    task_id=task.id,
                    db=db,
                )
                assert task.status == PLAN_PENDING_APPROVAL

                plan.status = "approved"
                await db.commit()
                task = await TaskReconciler().reconcile_task(
                    task_id=task.id,
                    db=db,
                )
                assert task.status == PLAN_APPROVED

                change_set = ChangeSet(
                    workspace_id=plan.workspace_id,
                    task_id=task.id,
                    plan_id=plan.id,
                    plan_version=1,
                    approved_plan_json=plan.plan_json,
                    status="generated",
                    base_commit_sha="a" * 40,
                    summary="Patch",
                    diff="diff --git a/a b/a\n",
                    diff_hash="b" * 64,
                    files_changed=1,
                    lines_added=1,
                    lines_deleted=0,
                )
                db.add(change_set)
                await db.commit()
                await db.refresh(change_set)

                run = ExecutionRun(
                    change_set_id=change_set.id,
                    workspace_id=plan.workspace_id,
                    task_id=task.id,
                    status="passed",
                    started_at=datetime.now(
                        UTC
                    ),
                    completed_at=datetime.now(
                        UTC
                    ),
                    duration_ms=1.0,
                    commands_json=[],
                    results_json=[],
                    timed_out=False,
                    sandbox_runtime="fake",
                )
                db.add(run)
                await db.commit()
                await db.refresh(run)

                task = await TaskReconciler().reconcile_task(
                    task_id=task.id,
                    db=db,
                )
                assert task.status == VERIFICATION_PASSED

                review = FinalReview(
                    workspace_id=plan.workspace_id,
                    task_id=task.id,
                    plan_id=plan.id,
                    change_set_id=change_set.id,
                    execution_run_id=run.id,
                    status="pending_review",
                    base_commit_sha="a" * 40,
                    diff_hash="b" * 64,
                    files_changed=1,
                    lines_added=1,
                    lines_deleted=0,
                    summary="Patch",
                    risk_summary="Low",
                    files_json=[],
                    verification_json={},
                    debug_history_json={},
                    issue_json={},
                    plan_snapshot_json={},
                    diff="diff",
                )
                db.add(review)
                await db.commit()
                await db.refresh(review)

                task = await TaskReconciler().reconcile_task(
                    task_id=task.id,
                    db=db,
                )
                assert task.status == REVIEW_PENDING

                review.status = "approved"
                await db.commit()
                task = await TaskReconciler().reconcile_task(
                    task_id=task.id,
                    db=db,
                )
                assert task.status == REVIEW_APPROVED

                publication = Publication(
                    workspace_id=plan.workspace_id,
                    task_id=task.id,
                    review_id=review.id,
                    plan_id=plan.id,
                    change_set_id=change_set.id,
                    status="published",
                    repository_owner="reconcile",
                    repository_name="repo",
                    base_branch="main",
                    branch_name="repopilot/202-test",
                    base_commit_sha="a" * 40,
                    approved_diff_hash="b" * 64,
                    commit_sha="c" * 40,
                    pull_request_number=1,
                    pull_request_url="https://example.test/pr/1",
                )
                db.add(publication)
                await db.commit()

                task = await TaskReconciler().reconcile_task(
                    task_id=task.id,
                    db=db,
                )
                assert task.status == COMPLETED

                with pytest.raises(
                    TaskTransitionError
                ):
                    await service.request_cancel(
                        task_id=task.id,
                        db=db,
                    )

            async with AsyncSessionLocal() as db:
                cancellable = await TaskService().create_task(
                    owner="cancel",
                    repo=f"repo{uuid.uuid4().hex[:8]}",
                    issue_number=303,
                    db=db,
                )
                created.append(cancellable.id)
                cancelled = await TaskService().request_cancel(
                    task_id=cancellable.id,
                    db=db,
                )
                assert cancelled.status == CANCELLED

            workspace_root = tmp_path / "workspaces"
            workspace_id = str(uuid.uuid4())
            workspace_path = workspace_root / workspace_id
            workspace_path.mkdir(
                parents=True
            )
            async with AsyncSessionLocal() as db:
                cleanup_task = await TaskService().create_task(
                    owner="cleanup",
                    repo=f"repo{uuid.uuid4().hex[:8]}",
                    issue_number=404,
                    db=db,
                )
                created.append(cleanup_task.id)
                cleanup_task.workspace_id = workspace_id
                cleanup_task.status = COMPLETED
                cleanup_task.completed_at = datetime.now(
                    UTC
                )
                await db.commit()
                await db.refresh(cleanup_task)

                result = await WorkspaceCleanupService(
                    workspaces_root=workspace_root
                ).cleanup_task_workspace(
                    task=cleanup_task,
                    db=db,
                )
                assert result["removed"] is True
                assert not workspace_path.exists()

                with pytest.raises(
                    CleanupSafetyError
                ):
                    WorkspaceCleanupService(
                        workspaces_root=workspace_root
                    ).safe_workspace_path(
                        "../escape"
                    )
        finally:
            await cleanup_task_records(
                created
            )
            await dispose_engines()

    asyncio.run(run_test())


def test_task_full_lifecycle_with_debug_reconciles_to_completed():
    created: list[uuid.UUID] = []

    async def run_test():
        try:
            async with AsyncSessionLocal() as db:
                service = TaskService()
                task = await service.create_task(
                    owner="fulldebug",
                    repo=f"repo{uuid.uuid4().hex[:8]}",
                    issue_number=707,
                    db=db,
                )
                created.append(task.id)
                output = valid_planner_output()
                workspace_id = str(
                    uuid.uuid4()
                )
                plan = ExecutionPlan(
                    workspace_id=workspace_id,
                    task_id=task.id,
                    repository_owner="fulldebug",
                    repository_name="repo",
                    issue_number=707,
                    status="approved",
                    summary=output.summary,
                    problem_analysis=(
                        output.problem_analysis
                    ),
                    likely_root_cause=(
                        output.likely_root_cause
                    ),
                    confidence=output.confidence,
                    plan_json=output.model_dump(
                        mode="json"
                    ),
                )
                db.add(plan)
                await db.commit()
                await db.refresh(plan)
                task = await TaskReconciler().reconcile_task(
                    task_id=task.id,
                    db=db,
                )
                assert task.status == PLAN_APPROVED

                initial_change_set = ChangeSet(
                    workspace_id=workspace_id,
                    task_id=task.id,
                    plan_id=plan.id,
                    plan_version=1,
                    approved_plan_json=plan.plan_json,
                    status="generated",
                    base_commit_sha="a" * 40,
                    summary="Initial patch",
                    diff="diff --git a/a b/a\n",
                    diff_hash="b" * 64,
                    files_changed=1,
                    lines_added=1,
                    lines_deleted=0,
                )
                db.add(initial_change_set)
                await db.commit()
                await db.refresh(initial_change_set)

                failed_run = ExecutionRun(
                    change_set_id=initial_change_set.id,
                    workspace_id=workspace_id,
                    task_id=task.id,
                    status="failed",
                    started_at=datetime.now(
                        UTC
                    ),
                    completed_at=datetime.now(
                        UTC
                    ),
                    duration_ms=10.0,
                    commands_json=[],
                    results_json=[
                        {
                            "name": "test",
                            "command_type": "test",
                            "status": "FAIL",
                            "exit_code": 1,
                            "duration_ms": 10.0,
                            "stdout": "",
                            "stderr": "failed",
                            "stdout_truncated": False,
                            "stderr_truncated": False,
                        }
                    ],
                    tests_status="FAIL",
                    timed_out=False,
                    sandbox_runtime="fake",
                )
                db.add(failed_run)
                await db.commit()
                await db.refresh(failed_run)
                task = await TaskReconciler().reconcile_task(
                    task_id=task.id,
                    db=db,
                )
                assert task.status == TEST_FAILED

                repair_change_set = ChangeSet(
                    workspace_id=workspace_id,
                    task_id=task.id,
                    plan_id=plan.id,
                    parent_change_set_id=(
                        initial_change_set.id
                    ),
                    plan_version=1,
                    approved_plan_json=plan.plan_json,
                    status="generated",
                    base_commit_sha="a" * 40,
                    summary="Debug repair",
                    diff="diff --git a/a b/a\n+fix\n",
                    diff_hash="d" * 64,
                    files_changed=1,
                    lines_added=2,
                    lines_deleted=0,
                )
                db.add(repair_change_set)
                await db.commit()
                await db.refresh(repair_change_set)

                debug_attempt = DebugAttempt(
                    workspace_id=workspace_id,
                    task_id=task.id,
                    plan_id=plan.id,
                    parent_change_set_id=(
                        initial_change_set.id
                    ),
                    new_change_set_id=(
                        repair_change_set.id
                    ),
                    failed_execution_run_id=(
                        failed_run.id
                    ),
                    attempt_number=1,
                    status="passed",
                    failure_category="test_failure",
                    started_at=datetime.now(
                        UTC
                    ),
                    completed_at=datetime.now(
                        UTC
                    ),
                )
                db.add(debug_attempt)
                await db.commit()

                passed_run = ExecutionRun(
                    change_set_id=repair_change_set.id,
                    workspace_id=workspace_id,
                    task_id=task.id,
                    status="passed",
                    started_at=datetime.now(
                        UTC
                    ),
                    completed_at=datetime.now(
                        UTC
                    ),
                    duration_ms=8.0,
                    commands_json=[],
                    results_json=[],
                    tests_status="PASS",
                    timed_out=False,
                    sandbox_runtime="fake",
                )
                db.add(passed_run)
                await db.commit()
                await db.refresh(passed_run)
                task = await TaskReconciler().reconcile_task(
                    task_id=task.id,
                    db=db,
                )
                assert task.status == VERIFICATION_PASSED
                assert (
                    task.active_execution_run_id
                    == passed_run.id
                )

                review = FinalReview(
                    workspace_id=workspace_id,
                    task_id=task.id,
                    plan_id=plan.id,
                    change_set_id=repair_change_set.id,
                    execution_run_id=passed_run.id,
                    status="approved",
                    base_commit_sha="a" * 40,
                    diff_hash="d" * 64,
                    files_changed=1,
                    lines_added=2,
                    lines_deleted=0,
                    summary="Debug repair",
                    risk_summary="Low",
                    files_json=[],
                    verification_json={},
                    debug_history_json={
                        "debug_attempts": 1
                    },
                    issue_json={},
                    plan_snapshot_json={},
                    diff="diff",
                )
                db.add(review)
                await db.commit()
                await db.refresh(review)
                task = await TaskReconciler().reconcile_task(
                    task_id=task.id,
                    db=db,
                )
                assert task.status == REVIEW_APPROVED

                publication = Publication(
                    workspace_id=workspace_id,
                    task_id=task.id,
                    review_id=review.id,
                    plan_id=plan.id,
                    change_set_id=repair_change_set.id,
                    status="published",
                    repository_owner="fulldebug",
                    repository_name="repo",
                    base_branch="main",
                    branch_name="repopilot/707-test",
                    base_commit_sha="a" * 40,
                    approved_diff_hash="d" * 64,
                    commit_sha="e" * 40,
                    pull_request_number=7,
                    pull_request_url="https://example.test/pr/7",
                )
                db.add(publication)
                await db.commit()

                task = await TaskReconciler().reconcile_task(
                    task_id=task.id,
                    db=db,
                )
                metrics = await TaskMetricsService().get_metrics(
                    task_id=task.id,
                    db=db,
                )
                events = list(
                    await db.scalars(
                        select(TaskEvent).where(
                            TaskEvent.task_id
                            == task.id
                        )
                    )
                )

                assert task.status == COMPLETED
                assert task.publication_id == publication.id
                assert metrics["debugging"][
                    "attempts"
                ] == 1
                assert len(events) >= 5
        finally:
            await cleanup_task_records(
                created
            )
            await dispose_engines()

    asyncio.run(run_test())


def test_task_api_create_get_timeline_metrics_and_cancel():
    task_id: uuid.UUID | None = None
    app.dependency_overrides[
        get_db
    ] = override_get_db
    app.dependency_overrides[
        get_github_client
    ] = override_github_client

    try:
        with TestClient(app) as test_client:
            suffix = uuid.uuid4().hex[:8]
            create_response = test_client.post(
                "/api/v1/tasks",
                json={
                    "owner": "apiowner",
                    "repo": f"repo{suffix}",
                    "issue_number": 505,
                },
                headers={
                    "X-Correlation-ID": "task-api-test"
                },
            )
            assert create_response.status_code == 200
            body = create_response.json()
            task_id = uuid.UUID(
                body["task_id"]
            )
            assert body["status"] == CREATED
            assert (
                create_response.headers[
                    "X-Correlation-ID"
                ]
                == "task-api-test"
            )

            get_response = test_client.get(
                f"/api/v1/tasks/{task_id}"
            )
            timeline_response = test_client.get(
                f"/api/v1/tasks/{task_id}/timeline"
            )
            metrics_response = test_client.get(
                f"/api/v1/tasks/{task_id}/metrics"
            )
            cancel_response = test_client.post(
                f"/api/v1/tasks/{task_id}/cancel"
            )

            assert get_response.status_code == 200
            assert timeline_response.status_code == 200
            assert metrics_response.status_code == 200
            assert cancel_response.status_code == 200
            assert cancel_response.json()[
                "status"
            ] == CANCELLED
            assert timeline_response.json()[
                "events"
            ][0]["event_type"] == "task.created"
    finally:
        app.dependency_overrides.pop(
            get_db,
            None,
        )
        app.dependency_overrides.pop(
            get_github_client,
            None,
        )
        async def cleanup():
            if task_id is not None:
                await cleanup_task_records(
                    [task_id]
                )
            await dispose_engines()

        asyncio.run(cleanup())
