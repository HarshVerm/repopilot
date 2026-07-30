# Module purpose: Implement workflow behavior for the task lifecycle domain.

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.coder.service import CodingService
from app.db.models.identity import GitHubInstallation, Repository
from app.db.session import AsyncSessionLocal
from app.services.debugging.orchestrator import DebugOrchestrator
from app.services.debugging.failure_classifier import (
    classify_execution_run,
)
from app.services.changes.git import get_base_commit_sha
from app.services.embeddings.client import OpenAIEmbeddingClient
from app.services.github.app_client import github_app_client
from app.services.indexing.indexer import index_repository
from app.services.planning.service import (
    PlannerService,
    issue_query_text,
)
from app.observability.logging import (
    log_task_event,
    log_task_failure,
)
from app.services.publishing.authentication import GitHubCredentials
from app.services.retrieval.service import (
    build_retrieval_index,
    hybrid_search,
)
from app.services.reviews.service import ReviewService
from app.services.sandbox.manager import ExecutionService
from app.services.sandbox.policy import (
    WorkspaceStateMismatchError,
)
from app.services.tasks.failures import (
    PATCH_POLICY_ERROR,
    UNKNOWN,
)
from app.services.tasks.locking import (
    TaskOperationConflict,
    TaskOperationLockService,
)
from app.services.tasks.service import (
    TaskService,
    task_issue_snapshot,
)
from app.services.tasks.state_machine import (
    CANCELLED,
    FAILED,
    INDEXED,
    INDEXING,
    PLAN_REVISION_REQUIRED,
    REPOSITORY_PREPARING,
    RETRIEVING,
    TERMINAL_STATES,
)
from app.services.workspace.manager import (
    WORKSPACES_DIR,
    workspace_manager,
)


class TaskWorkflowService:
    """Runs the existing agent services in the Standard autonomy order."""

    # Purpose: Run task for the task lifecycle workflow.
    async def run_task(self, task_id: uuid.UUID) -> None:
        async with AsyncSessionLocal() as db:
            lock = TaskOperationLockService()
            claim_lock_held = False
            try:
                await lock.acquire(
                    task_id=task_id,
                    operation="workflow",
                    db=db,
                )
                claim_lock_held = True
                task = await TaskService().require_task(
                    task_id=task_id,
                    db=db,
                )
                if task.status != "created":
                    log_task_event(
                        "workflow.skipped",
                        task_id=str(task_id),
                        current_status=task.status,
                        reason="task_not_created",
                    )
                    await lock.release(
                        task_id=task_id,
                        operation="workflow",
                        db=db,
                    )
                    claim_lock_held = False
                    return
                await TaskService().transition_task(
                    task_id=task_id,
                    new_status=REPOSITORY_PREPARING,
                    db=db,
                    event_type="workflow.started",
                )
                await lock.release(
                    task_id=task_id,
                    operation="workflow",
                    db=db,
                )
                claim_lock_held = False
                await self._run(task_id=task_id, db=db)
            except TaskOperationConflict:
                # A duplicate create/start request is already executing.
                log_task_event(
                    "workflow.skipped",
                    task_id=str(task_id),
                    reason="workflow_lock_already_held",
                )
                return
            except Exception as exc:
                await self._record_failure(
                    task_id=task_id,
                    error=exc,
                    db=db,
                )
            finally:
                if claim_lock_held:
                    await lock.release(
                        task_id=task_id,
                        operation="workflow",
                        db=db,
                    )

    # Purpose: Run task lifecycle for the task lifecycle workflow.
    async def _run(
        self,
        *,
        task_id: uuid.UUID,
        db: AsyncSession,
    ) -> None:
        task_service = TaskService()
        task = await task_service.require_task(
            task_id=task_id,
            db=db,
        )
        if (
            task.user_id is None
            or task.repository_id is None
            or task.installation_id is None
        ):
            raise RuntimeError(
                "Automatic workflow requires a GitHub-native task"
            )
        repository = await db.get(
            Repository,
            task.repository_id,
        )
        installation = await db.get(
            GitHubInstallation,
            task.installation_id,
        )
        if (
            repository is None
            or installation is None
            or installation.user_id != task.user_id
            or installation.status != "active"
            or repository.access_status != "active"
        ):
            raise RuntimeError(
                "GitHub repository access is no longer active"
            )

        token = await github_app_client.create_installation_token(
            installation.github_installation_id
        )
        credentials = GitHubCredentials(
            username="x-access-token",
            token=token,
        )
        workspace_id = str(task.id)
        repository_path = (
            WORKSPACES_DIR / workspace_id / "repository"
        )

        await self._check_cancel(task_id, db)
        if not repository_path.exists():
            await task_service.record_event(
                task_id=task_id,
                event_type="repository.clone.started",
                db=db,
                metadata={
                    "repository_id": str(repository.id),
                },
                commit=True,
            )
            await workspace_manager.clone_repository(
                repository.clone_url
                or (
                    "https://github.com/"
                    f"{repository.full_name}.git"
                ),
                workspace_id=workspace_id,
                credentials=credentials,
            )
        await task_service.attach_workspace(
            task_id=task_id,
            workspace_id=workspace_id,
            db=db,
        )
        task = await task_service.require_task(
            task_id=task_id,
            db=db,
        )
        task.base_commit_sha = get_base_commit_sha(
            repository_path
        )
        await db.commit()
        await task_service.record_event(
            task_id=task_id,
            event_type="repository.base_captured",
            db=db,
            metadata={
                "base_branch": task.base_branch,
                "base_commit_sha": task.base_commit_sha,
            },
            commit=True,
        )

        await self._check_cancel(task_id, db)
        await task_service.transition_task(
            task_id=task_id,
            new_status=INDEXING,
            db=db,
            event_type="indexing.started",
        )
        # Build the file/symbol index that the chunking stage reads.
        index_result = await index_repository(
            workspace_id=workspace_id,
            repository_path=repository_path,
            db=db,
        )
        await task_service.transition_task(
            task_id=task_id,
            new_status=INDEXED,
            db=db,
            event_type="indexing.completed",
            metadata=index_result,
        )

        # Create per-task chunks and vectors for hybrid RAG retrieval.
        embedding_client = OpenAIEmbeddingClient()
        await build_retrieval_index(
            workspace_id=workspace_id,
            repository_path=repository_path,
            db=db,
            embedding_client=embedding_client,
        )
        await self._check_cancel(task_id, db)
        await task_service.transition_task(
            task_id=task_id,
            new_status=RETRIEVING,
            db=db,
            event_type="retrieval.started",
        )
        issue = task_issue_snapshot(task)
        # Retrieve issue-relevant code and package it for the AI agents.
        context = await hybrid_search(
            workspace_id=workspace_id,
            query=issue_query_text(issue),
            top_k=10,
            db=db,
            embedding_client=embedding_client,
            debug=False,
        )
        await task_service.record_event(
            task_id=task_id,
            event_type="retrieval.completed",
            db=db,
            metadata={
                "result_count": len(context.get("results", [])),
                "estimated_tokens": (
                    context.get("context", {}).get(
                        "estimated_tokens",
                        0,
                    )
                ),
            },
            commit=True,
        )

        await self._check_cancel(task_id, db)
        plan = await PlannerService().create_plan(
            workspace_id=workspace_id,
            repository_path=repository_path,
            owner=repository.owner,
            repo=repository.name,
            issue=issue,
            context_pack=context["context"],
            db=db,
            task_id=task_id,
        )
        if plan.status != "approved":
            # Strict tasks intentionally stop at the existing plan gate.
            log_task_event(
                "workflow.stopped",
                task_id=str(task_id),
                stage="planning",
                reason="plan_not_approved",
                plan_id=str(plan.id),
                plan_status=plan.status,
            )
            return

        await self._check_cancel(task_id, db)
        change_set = await CodingService().implement_plan(
            plan=plan,
            repository_path=repository_path,
            issue=issue,
            context_pack=context["context"],
            db=db,
            task_id=task_id,
        )
        if change_set.status != "generated":
            log_task_event(
                "workflow.stopped",
                task_id=str(task_id),
                stage="coding",
                reason="change_set_not_generated",
                change_set_id=str(change_set.id),
                change_set_status=change_set.status,
            )
            return

        await self._check_cancel(task_id, db)
        run = await ExecutionService().execute_change_set(
            change_set_id=change_set.id,
            repository_path=repository_path,
            db=db,
            task_id=task_id,
        )
        final_change_set_id = change_set.id
        final_run_id = run.id
        if run.status != "passed":
            classification = classify_execution_run(
                run
            )
            if not classification.eligible:
                log_task_event(
                    "workflow.stopped",
                    task_id=str(task_id),
                    stage="verification",
                    reason=classification.category,
                    execution_run_id=str(run.id),
                    execution_status=run.status,
                    detail=classification.reason,
                )
                return
            result = await DebugOrchestrator().debug_execution_run(
                execution_run_id=run.id,
                repository_path=repository_path,
                db=db,
                task_id=task_id,
            )
            if result.status != "passed":
                log_task_event(
                    "workflow.stopped",
                    task_id=str(task_id),
                    stage="debugging",
                    reason="debugging_did_not_pass",
                    debug_status=result.status,
                    execution_run_id=str(run.id),
                )
                return
            final_change_set_id = (
                result.final_change_set_id
                or final_change_set_id
            )
            final_run_id = (
                result.final_execution_run_id
                or final_run_id
            )

        await self._check_cancel(task_id, db)
        final_run = await ExecutionService().get_execution_run(
            execution_run_id=final_run_id,
            db=db,
        )
        if final_run is None or final_run.status != "passed":
            log_task_event(
                "workflow.stopped",
                task_id=str(task_id),
                stage="verification",
                reason="final_execution_not_passed",
                execution_run_id=str(final_run_id),
                execution_status=(
                    final_run.status
                    if final_run is not None
                    else "missing"
                ),
            )
            return
        await ReviewService().create_review(
            change_set_id=final_change_set_id,
            repository_path=repository_path,
            db=db,
            task_id=task_id,
        )

    # Purpose: Run revision for the task lifecycle workflow.
    async def run_revision(
        self,
        *,
        task_id: uuid.UUID,
        previous_change_set_id: uuid.UUID,
        review_feedback: str,
    ) -> None:
        async with AsyncSessionLocal() as db:
            try:
                task = await TaskService().require_task(
                    task_id=task_id,
                    db=db,
                )
                if (
                    task.status != "coding"
                    or task.active_plan_id is None
                    or task.workspace_id is None
                ):
                    log_task_event(
                        "workflow.revision.skipped",
                        task_id=str(task_id),
                        current_status=task.status,
                        has_active_plan=(
                            task.active_plan_id is not None
                        ),
                        has_workspace=(
                            task.workspace_id is not None
                        ),
                        reason="revision_prerequisites_missing",
                    )
                    return
                from app.db.models.execution_plan import ExecutionPlan

                plan = await db.get(
                    ExecutionPlan,
                    task.active_plan_id,
                )
                if plan is None or plan.status != "approved":
                    raise RuntimeError(
                        "Approved plan not found for review revision"
                    )
                repository_path = (
                    WORKSPACES_DIR
                    / task.workspace_id
                    / "repository"
                )
                issue = task_issue_snapshot(task)
                embedding_client = OpenAIEmbeddingClient()
                context = await hybrid_search(
                    workspace_id=task.workspace_id,
                    query=issue_query_text(issue),
                    top_k=10,
                    db=db,
                    embedding_client=embedding_client,
                    debug=False,
                )
                change_set = await CodingService().implement_plan(
                    plan=plan,
                    repository_path=repository_path,
                    issue=issue,
                    context_pack=context["context"],
                    db=db,
                    task_id=task_id,
                    previous_change_set_id=(
                        previous_change_set_id
                    ),
                    review_feedback=review_feedback,
                )
                if change_set.status != "generated":
                    log_task_event(
                        "workflow.revision.stopped",
                        task_id=str(task_id),
                        stage="coding",
                        reason="change_set_not_generated",
                        change_set_id=str(change_set.id),
                        change_set_status=change_set.status,
                    )
                    return
                run = await ExecutionService().execute_change_set(
                    change_set_id=change_set.id,
                    repository_path=repository_path,
                    db=db,
                    task_id=task_id,
                )
                final_change_set_id = change_set.id
                final_run_id = run.id
                if run.status != "passed":
                    classification = classify_execution_run(
                        run
                    )
                    if not classification.eligible:
                        log_task_event(
                            "workflow.revision.stopped",
                            task_id=str(task_id),
                            stage="verification",
                            reason=classification.category,
                            execution_run_id=str(run.id),
                            execution_status=run.status,
                            detail=classification.reason,
                        )
                        return
                    result = (
                        await DebugOrchestrator().debug_execution_run(
                            execution_run_id=run.id,
                            repository_path=repository_path,
                            db=db,
                            task_id=task_id,
                        )
                    )
                    if result.status != "passed":
                        log_task_event(
                            "workflow.revision.stopped",
                            task_id=str(task_id),
                            stage="debugging",
                            reason="debugging_did_not_pass",
                            debug_status=result.status,
                            execution_run_id=str(run.id),
                        )
                        return
                    final_change_set_id = (
                        result.final_change_set_id
                        or final_change_set_id
                    )
                    final_run_id = (
                        result.final_execution_run_id
                        or final_run_id
                    )
                final_run = (
                    await ExecutionService().get_execution_run(
                        execution_run_id=final_run_id,
                        db=db,
                    )
                )
                if final_run is None or final_run.status != "passed":
                    log_task_event(
                        "workflow.revision.stopped",
                        task_id=str(task_id),
                        stage="verification",
                        reason="final_execution_not_passed",
                        execution_run_id=str(final_run_id),
                        execution_status=(
                            final_run.status
                            if final_run is not None
                            else "missing"
                        ),
                    )
                    return
                await ReviewService().create_review(
                    change_set_id=final_change_set_id,
                    repository_path=repository_path,
                    db=db,
                    task_id=task_id,
                )
            except Exception as exc:
                await self._record_failure(
                    task_id=task_id,
                    error=exc,
                    db=db,
                )

    # Purpose: Check cancel for the task lifecycle workflow.
    async def _check_cancel(
        self,
        task_id: uuid.UUID,
        db: AsyncSession,
    ) -> None:
        task = await TaskService().require_task(
            task_id=task_id,
            db=db,
        )
        if task.cancel_requested or task.status == CANCELLED:
            raise WorkflowCancelled()

    # Purpose: Record failure for the task lifecycle workflow.
    async def _record_failure(
        self,
        *,
        task_id: uuid.UUID,
        error: Exception,
        db: AsyncSession,
    ) -> None:
        task = await TaskService().get_task(
            task_id=task_id,
            db=db,
        )
        current_status = (
            task.status
            if task is not None
            else "missing"
        )
        if isinstance(error, WorkflowCancelled):
            log_task_event(
                "workflow.stopped",
                task_id=str(task_id),
                current_status=current_status,
                reason="cancelled",
            )
            return
        if (
            task is None
            or task.status in TERMINAL_STATES
            or task.status == PLAN_REVISION_REQUIRED
        ):
            log_task_event(
                "workflow.stopped",
                task_id=str(task_id),
                current_status=current_status,
                reason="failure_already_recorded",
                error_type=error.__class__.__name__,
                error_message=str(error),
            )
            return
        try:
            failure_category = UNKNOWN
            public_message = None
            if isinstance(
                error,
                WorkspaceStateMismatchError,
            ):
                failure_category = PATCH_POLICY_ERROR
                public_message = str(error)
            await TaskService().set_failure(
                task_id=task_id,
                db=db,
                failure_category=failure_category,
                error=error,
                public_message=public_message,
                event_type="workflow.failed",
            )
        except Exception as record_error:
            await db.rollback()
            log_task_failure(
                "workflow.failure_recording_failed",
                record_error,
                task_id=str(task_id),
                original_error_type=error.__class__.__name__,
                original_error_message=str(error),
            )


# Purpose: Encapsulate workflow cancelled behavior for the task lifecycle domain.
class WorkflowCancelled(RuntimeError):
    pass


# Purpose: Run task background for the task lifecycle workflow.
async def run_task_background(task_id: str) -> None:
    await TaskWorkflowService().run_task(
        uuid.UUID(task_id)
    )


# Purpose: Run revision background for the task lifecycle workflow.
async def run_revision_background(
    task_id: str,
    previous_change_set_id: str,
    review_feedback: str,
) -> None:
    await TaskWorkflowService().run_revision(
        task_id=uuid.UUID(task_id),
        previous_change_set_id=uuid.UUID(
            previous_change_set_id
        ),
        review_feedback=review_feedback,
    )
