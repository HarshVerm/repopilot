# Module purpose: Define tasks HTTP API routes.

from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
)
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.task_event import TaskEvent
from app.db.models.identity import User
from app.db.session import get_db
from app.schemas.tasks import (
    CancelTaskResponse,
    CreateTaskRequest,
    ReconcileTaskResponse,
    TaskListResponse,
    TaskMetricsResponse,
    TaskResponse,
    TaskTimelineResponse,
)
from app.services.github.client import (
    github_client,
)
from app.services.github.app_client import (
    GitHubAppClient,
    github_app_client,
)
from app.services.github.installations import (
    installation_http_error,
)
from app.services.auth.service import (
    AuthContext,
    auth_error,
    get_optional_auth_context,
    validate_csrf_tokens,
)
from app.api.routes.github import (
    resolve_user_repository,
)
from app.core.config import settings
from app.services.hardening.rate_limit import (
    enforce_rate_limit,
)
from app.services.tasks.metrics import (
    TaskMetricsService,
)
from app.services.tasks.reconciler import (
    TaskReconciler,
)
from app.services.tasks.service import (
    TaskNotFoundError,
    TaskService,
    TaskValidationError,
    serialize_task,
    serialize_timeline_event,
)
from app.services.tasks.state_machine import (
    CANCELLED,
    FAILED,
    PLAN_REVISION_REQUIRED,
    TASK_STATUSES,
    TaskConcurrencyError,
    TaskTransitionError,
)
from app.services.tasks.workflow import (
    run_task_background,
)


router = APIRouter(
    prefix="/tasks",
    tags=["tasks"],
)


# Purpose: Return github client for the task lifecycle workflow.
def get_github_client():
    return github_client


# Purpose: Return github app client for the task lifecycle workflow.
def get_github_app_client() -> GitHubAppClient:
    return github_app_client


# Purpose: Create task for the task lifecycle workflow.
@router.post(
    "",
    response_model=TaskResponse,
    dependencies=[
        Depends(
            enforce_rate_limit(
                "task_create"
            )
        )
    ],
)
async def create_task(
    request: CreateTaskRequest,
    http_request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext | None = Depends(
        get_optional_auth_context
    ),
    github=Depends(
        get_github_client
    ),
    github_app: GitHubAppClient = Depends(
        get_github_app_client
    ),
):
    try:
        if request.repository_id is not None:
            if auth is None:
                raise auth_error(
                    status_code=401,
                    code="AUTH_REQUIRED",
                    message="Sign in with GitHub to create a task.",
                )
            validate_csrf_tokens(
                request=http_request,
                context=auth,
            )
            repository, installation = (
                await resolve_user_repository(
                    repository_id=request.repository_id,
                    user_id=auth.user.id,
                    db=db,
                )
            )
            if repository.archived:
                raise auth_error(
                    status_code=409,
                    code="REPOSITORY_ARCHIVED",
                    message="Archived repositories cannot start new tasks.",
                )
            if repository.disabled:
                raise auth_error(
                    status_code=409,
                    code="REPOSITORY_ACCESS_DENIED",
                    message="This GitHub repository is disabled.",
                )
            issue = await github_app.get_issue(
                installation.github_installation_id,
                repository.owner,
                repository.name,
                request.issue_number,
            )
            if "pull_request" in issue:
                raise auth_error(
                    status_code=404,
                    code="ISSUE_NOT_FOUND",
                    message="GitHub issue not found.",
                )
            task = await TaskService().create_task(
                owner=repository.owner,
                repo=repository.name,
                issue_number=request.issue_number,
                db=db,
                user_id=auth.user.id,
                installation_id=installation.id,
                repository_id=repository.id,
                issue_snapshot=issue,
                issue_summary=derive_issue_summary(issue),
                user_instructions=(
                    request.user_instructions.strip()
                    if request.user_instructions
                    else None
                ),
                base_branch=repository.default_branch,
                autonomy_mode="standard",
            )
            await TaskService().record_event(
                task_id=task.id,
                event_type="issue.snapshot.persisted",
                db=db,
                metadata={
                    "issue_number": request.issue_number,
                    "github_issue_id": issue.get("id"),
                },
                commit=True,
            )
            # Recording the event updates ``task.last_event_at``. SQLAlchemy's
            # on-update value expires ``updated_at`` during that commit, so
            # refresh before synchronous response serialization accesses it.
            await db.refresh(task)
            background_tasks.add_task(
                run_task_background,
                str(task.id),
            )
        else:
            require_legacy_api()
            assert request.owner is not None
            assert request.repo is not None
            await github.get_repository(
                request.owner,
                request.repo,
            )
            task = await TaskService().create_task(
                owner=request.owner,
                repo=request.repo,
                issue_number=request.issue_number,
                db=db,
            )
    except TaskValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail=(
                    "Issue not found"
                    if request.repository_id
                    else "Repository not found"
                ),
            ) from exc

        if request.repository_id:
            raise installation_http_error(exc) from exc
        raise HTTPException(
            status_code=502,
            detail="GitHub repository retrieval failed",
        ) from exc

    return serialize_task(
        task
    )


# Purpose: List tasks for the task lifecycle workflow.
@router.get(
    "",
    response_model=TaskListResponse,
)
async def list_tasks(
    status: Annotated[
        str | None,
        Query(
            pattern="|".join(TASK_STATUSES)
        ),
    ] = None,
    owner: str | None = None,
    repo: str | None = None,
    issue_number: int | None = None,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=100,
        ),
    ] = 50,
    offset: Annotated[
        int,
        Query(
            ge=0,
        ),
    ] = 0,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext | None = Depends(
        get_optional_auth_context
    ),
):
    if auth is None:
        require_legacy_api()
    tasks = await TaskService().list_tasks(
        db=db,
        status=status,
        owner=owner,
        repo=repo,
        issue_number=issue_number,
        limit=limit,
        offset=offset,
        user_id=(
            auth.user.id
            if auth
            else None
        ),
    )
    return {
        "tasks": [
            serialize_task(task)
            for task in tasks
        ]
    }


# Purpose: Return task for the task lifecycle workflow.
@router.get(
    "/{task_id}",
    response_model=TaskResponse,
)
async def get_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext | None = Depends(
        get_optional_auth_context
    ),
):
    task = await authorized_task(
        task_id=task_id,
        auth=auth,
        db=db,
    )

    if task is None:
        raise HTTPException(
            status_code=404,
            detail="Task not found",
        )

    metrics = await TaskMetricsService().get_metrics(
        task_id=task.id,
        db=db,
    )

    return serialize_task(
        task,
        metrics=summarize_metrics(
            metrics
        ),
    )


# Purpose: Return task timeline for the task lifecycle workflow.
@router.get(
    "/{task_id}/timeline",
    response_model=TaskTimelineResponse,
)
async def get_task_timeline(
    task_id: UUID,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=200,
        ),
    ] = 100,
    offset: Annotated[
        int,
        Query(
            ge=0,
        ),
    ] = 0,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext | None = Depends(
        get_optional_auth_context
    ),
):
    task = await authorized_task(
        task_id=task_id,
        auth=auth,
        db=db,
    )

    if task is None:
        raise HTTPException(
            status_code=404,
            detail="Task not found",
        )

    events = list(
        await db.scalars(
            select(TaskEvent)
            .where(
                TaskEvent.task_id == task_id
            )
            .order_by(
                TaskEvent.created_at,
                TaskEvent.id,
            )
            .limit(limit)
            .offset(offset)
        )
    )

    return {
        "task_id": str(task_id),
        "events": [
            serialize_timeline_event(event)
            for event in events
        ],
    }


# Purpose: Return task metrics for the task lifecycle workflow.
@router.get(
    "/{task_id}/metrics",
    response_model=TaskMetricsResponse,
)
async def get_task_metrics(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext | None = Depends(
        get_optional_auth_context
    ),
):
    task = await authorized_task(
        task_id=task_id,
        auth=auth,
        db=db,
    )

    if task is None:
        raise HTTPException(
            status_code=404,
            detail="Task not found",
        )

    return {
        "task_id": str(task_id),
        "metrics": await TaskMetricsService().get_metrics(
            task_id=task_id,
            db=db,
        ),
    }


# Purpose: Cancel task for the task lifecycle workflow.
@router.post(
    "/{task_id}/cancel",
    response_model=CancelTaskResponse,
)
async def cancel_task(
    task_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext | None = Depends(
        get_optional_auth_context
    ),
):
    try:
        await authorized_task(
            task_id=task_id,
            auth=auth,
            db=db,
        )
        require_mutation_access(
            request=request,
            auth=auth,
        )
        task = await TaskService().request_cancel(
            task_id=task_id,
            db=db,
        )
    except TaskNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Task not found",
        ) from exc
    except TaskTransitionError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    return CancelTaskResponse(
        task_id=str(task.id),
        status=task.status,
        cancel_requested=task.cancel_requested,
    )


# Purpose: Handle restart task for the task lifecycle workflow.
@router.post(
    "/{task_id}/restart",
    response_model=TaskResponse,
    dependencies=[
        Depends(
            enforce_rate_limit(
                "task_create"
            )
        )
    ],
)
async def restart_task(
    task_id: UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext | None = Depends(
        get_optional_auth_context
    ),
    github_app: GitHubAppClient = Depends(
        get_github_app_client
    ),
):
    task = await authorized_task(
        task_id=task_id,
        auth=auth,
        db=db,
    )
    require_mutation_access(
        request=request,
        auth=auth,
    )

    prior_status = task.status
    if prior_status not in {
        FAILED,
        CANCELLED,
        PLAN_REVISION_REQUIRED,
    }:
        raise HTTPException(
            status_code=409,
            detail=(
                "Only failed, cancelled, or plan-revision tasks can be restarted"
            ),
        )
    if (
        auth is None
        or task.repository_id is None
        or task.installation_id is None
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "Only GitHub-native tasks can be restarted"
            ),
        )

    repository, installation = (
        await resolve_user_repository(
            repository_id=task.repository_id,
            user_id=auth.user.id,
            db=db,
        )
    )
    if repository.archived:
        raise auth_error(
            status_code=409,
            code="REPOSITORY_ARCHIVED",
            message="Archived repositories cannot restart tasks.",
        )
    if repository.disabled:
        raise auth_error(
            status_code=409,
            code="REPOSITORY_ACCESS_DENIED",
            message="This GitHub repository is disabled.",
        )
    try:
        issue = await github_app.get_issue(
            installation.github_installation_id,
            repository.owner,
            repository.name,
            task.issue_number,
        )
    except httpx.HTTPStatusError as exc:
        raise installation_http_error(
            exc
        ) from exc

    if "pull_request" in issue:
        raise auth_error(
            status_code=404,
            code="ISSUE_NOT_FOUND",
            message="GitHub issue not found.",
        )

    task_service = TaskService()
    if prior_status == PLAN_REVISION_REQUIRED:
        task = await task_service.transition_task(
            task_id=task.id,
            new_status=CANCELLED,
            db=db,
            event_type="task.restart_superseded",
            metadata={
                "prior_status": prior_status,
                "reason": "new_planning_attempt",
            },
        )
    restarted = await task_service.create_task(
        owner=repository.owner,
        repo=repository.name,
        issue_number=task.issue_number,
        db=db,
        user_id=auth.user.id,
        installation_id=installation.id,
        repository_id=repository.id,
        issue_snapshot=issue,
        issue_summary=derive_issue_summary(
            issue
        ),
        user_instructions=task.user_instructions,
        base_branch=repository.default_branch,
        autonomy_mode=task.autonomy_mode,
    )
    await task_service.record_event(
        task_id=task.id,
        event_type="task.restart_requested",
        db=db,
        metadata={
            "restarted_task_id": str(
                restarted.id
            ),
            "prior_status": prior_status,
            "prior_failure_category": (
                task.failure_category
            ),
        },
        commit=True,
    )
    await task_service.record_event(
        task_id=restarted.id,
        event_type="task.restarted",
        db=db,
        metadata={
            "restarted_from_task_id": str(
                task.id
            ),
        },
        commit=True,
    )
    await db.refresh(restarted)
    background_tasks.add_task(
        run_task_background,
        str(restarted.id),
    )
    return serialize_task(
        restarted
    )


# Purpose: Reconcile task for the task lifecycle workflow.
@router.post(
    "/{task_id}/reconcile",
    response_model=ReconcileTaskResponse,
)
async def reconcile_task(
    task_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext | None = Depends(
        get_optional_auth_context
    ),
):
    try:
        await authorized_task(
            task_id=task_id,
            auth=auth,
            db=db,
        )
        require_mutation_access(
            request=request,
            auth=auth,
        )
        task = await TaskReconciler().reconcile_task(
            task_id=task_id,
            db=db,
        )
    except TaskNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Task not found",
        ) from exc
    except TaskConcurrencyError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    return {
        "task": serialize_task(task)
    }


# Purpose: Summarize metrics for the task lifecycle workflow.
def summarize_metrics(
    metrics: dict,
) -> dict:
    return {
        "agent_tokens": metrics["agents"][
            "total"
        ]["total_tokens"],
        "agent_latency_ms": metrics["agents"][
            "total"
        ]["latency_ms"],
        "sandbox_runs": metrics["sandbox"][
            "runs"
        ],
        "debug_attempts": metrics["debugging"][
            "attempts"
        ],
    }


# Purpose: Handle authorized task for the task lifecycle workflow.
async def authorized_task(
    *,
    task_id: UUID,
    auth: AuthContext | None,
    db: AsyncSession,
):
    if auth is None:
        require_legacy_api()
    task = await TaskService().get_user_task(
        task_id=task_id,
        user_id=auth.user.id if auth else None,
        db=db,
    )
    if task is None:
        raise HTTPException(
            status_code=404,
            detail="Task not found",
        )
    return task


# Purpose: Require mutation access, raising an error when unavailable.
def require_mutation_access(
    *,
    request: Request,
    auth: AuthContext | None,
) -> User | None:
    if auth is None:
        require_legacy_api()
        return None
    validate_csrf_tokens(
        request=request,
        context=auth,
    )
    return auth.user


# Purpose: Require legacy api, raising an error when unavailable.
def require_legacy_api() -> None:
    if not settings.allow_legacy_unauthenticated_api:
        raise auth_error(
            status_code=401,
            code="AUTH_REQUIRED",
            message="Sign in with GitHub to continue.",
        )


# Purpose: Derive issue summary for the task lifecycle workflow.
def derive_issue_summary(issue: dict) -> str:
    title = str(issue.get("title") or "GitHub issue").strip()
    body = str(issue.get("body") or "").strip()
    body_excerpt = body[:1200] or (
        "No issue body was provided; use the title and repository "
        "context to determine the expected behavior."
    )
    labels = ", ".join(
        str(
            label.get("name")
            if isinstance(label, dict)
            else label
        )
        for label in issue.get("labels", [])
    )
    constraints = (
        f"Issue labels: {labels}."
        if labels
        else "Preserve existing behavior and security constraints."
    )
    return (
        f"Problem\n{title}\n\n"
        f"Expected Behaviour\n{body_excerpt}\n\n"
        "Likely Area\nDetermine from repository retrieval and code analysis.\n\n"
        "Success Criteria\n"
        "- Address the issue's observable behavior.\n"
        "- Add or update regression coverage where appropriate.\n"
        "- Pass the repository's configured verification checks.\n\n"
        f"Important Constraints\n{constraints}"
    )
