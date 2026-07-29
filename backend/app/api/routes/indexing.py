from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
)

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.code_index import (
    CodeSymbol,
    RepositoryFile,
)
from app.db.session import get_db
from app.schemas.indexing import (
    IndexResponse,
    SymbolSearchResult,
)
from app.services.indexing.indexer import (
    index_repository,
)
from app.services.tasks.failures import (
    INDEXING_ERROR,
)
from app.services.tasks.service import (
    TaskService,
)
from app.services.tasks.state_machine import (
    INDEXED,
    INDEXING,
    TaskTransitionError,
)

router = APIRouter(
    prefix="/index",
    tags=["indexing"],
)


PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[4]
)

WORKSPACES_DIR = (
    PROJECT_ROOT / "workspaces"
)

MAX_SYMBOL_QUERY_LENGTH = 100
MAX_SYMBOL_SEARCH_LIMIT = 50


def escape_like_query(
    query: str,
) -> str:
    return (
        query
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


@router.post(
    "/{workspace_id}",
    response_model=IndexResponse,
)
async def create_index(
    workspace_id: UUID,
    db: AsyncSession = Depends(get_db),
):

    repository_path = (
        WORKSPACES_DIR
        / str(workspace_id)
        / "repository"
    )

    if not repository_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Workspace not found",
        )

    task_service = TaskService()
    task = await task_service.find_task_by_workspace(
        workspace_id=str(workspace_id),
        db=db,
    )

    try:
        if task is not None:
            try:
                await task_service.transition_task(
                    task_id=task.id,
                    new_status=INDEXING,
                    db=db,
                    event_type="indexing.started",
                    metadata={
                        "workspace_id": str(
                            workspace_id
                        )
                    },
                )
            except TaskTransitionError:
                await task_service.record_event(
                    task_id=task.id,
                    event_type="indexing.started",
                    db=db,
                    metadata={
                        "workspace_id": str(
                            workspace_id
                        ),
                        "status": task.status,
                    },
                    commit=True,
                )

        result = await index_repository(
            workspace_id=str(workspace_id),
            repository_path=repository_path,
            db=db,
        )

        if task is not None:
            try:
                await task_service.transition_task(
                    task_id=task.id,
                    new_status=INDEXED,
                    db=db,
                    event_type="indexing.completed",
                    metadata=result,
                )
            except TaskTransitionError:
                await task_service.record_event(
                    task_id=task.id,
                    event_type="indexing.completed",
                    db=db,
                    metadata=result,
                    commit=True,
                )
    except Exception as exc:
        if task is not None:
            await task_service.set_failure(
                task_id=task.id,
                db=db,
                failure_category=INDEXING_ERROR,
                error=exc,
                event_type="indexing.failed",
            )
        raise

    return {
        "workspace_id": str(workspace_id),
        **result,
    }


@router.get(
    "/{workspace_id}/symbols",
    response_model=list[SymbolSearchResult],
)
async def search_symbols(
    workspace_id: UUID,
    q: Annotated[
        str,
        Query(
            min_length=1,
            max_length=MAX_SYMBOL_QUERY_LENGTH,
        ),
    ],
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=MAX_SYMBOL_SEARCH_LIMIT,
        ),
    ] = 20,
    db: AsyncSession = Depends(get_db),
):
    query = q.strip()

    if not query:
        raise HTTPException(
            status_code=422,
            detail="Query must not be blank",
        )

    pattern = f"%{escape_like_query(query)}%"

    result = await db.execute(
        select(
            CodeSymbol.name,
            CodeSymbol.kind,
            RepositoryFile.file_path,
            RepositoryFile.language,
            CodeSymbol.start_line,
            CodeSymbol.end_line,
        )
        .join(
            RepositoryFile,
            CodeSymbol.file_id == RepositoryFile.id,
        )
        .where(
            RepositoryFile.workspace_id
            == str(workspace_id),
            CodeSymbol.name.ilike(
                pattern,
                escape="\\",
            ),
        )
        .order_by(
            CodeSymbol.name,
            RepositoryFile.file_path,
            CodeSymbol.start_line,
        )
        .limit(limit)
    )

    return [
        SymbolSearchResult(
            name=row.name,
            kind=row.kind,
            file_path=row.file_path,
            language=row.language,
            start_line=row.start_line,
            end_line=row.end_line,
        )
        for row in result.all()
    ]
