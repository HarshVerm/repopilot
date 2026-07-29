from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
)
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.task_event import TaskEvent
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
    TASK_STATUSES,
    TaskConcurrencyError,
    TaskTransitionError,
)


router = APIRouter(
    prefix="/tasks",
    tags=["tasks"],
)


def get_github_client():
    return github_client


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
    db: AsyncSession = Depends(get_db),
    github=Depends(
        get_github_client
    ),
):
    try:
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
                detail="Repository not found",
            ) from exc

        raise HTTPException(
            status_code=502,
            detail="GitHub repository retrieval failed",
        ) from exc

    return serialize_task(
        task
    )


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
):
    tasks = await TaskService().list_tasks(
        db=db,
        status=status,
        owner=owner,
        repo=repo,
        issue_number=issue_number,
        limit=limit,
        offset=offset,
    )
    return {
        "tasks": [
            serialize_task(task)
            for task in tasks
        ]
    }


@router.get(
    "/{task_id}",
    response_model=TaskResponse,
)
async def get_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    task = await TaskService().get_task(
        task_id=task_id,
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
):
    task = await TaskService().get_task(
        task_id=task_id,
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


@router.get(
    "/{task_id}/metrics",
    response_model=TaskMetricsResponse,
)
async def get_task_metrics(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    task = await TaskService().get_task(
        task_id=task_id,
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


@router.post(
    "/{task_id}/cancel",
    response_model=CancelTaskResponse,
)
async def cancel_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    try:
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


@router.post(
    "/{task_id}/reconcile",
    response_model=ReconcileTaskResponse,
)
async def reconcile_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    try:
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
