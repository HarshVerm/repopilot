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

    result = await index_repository(
        workspace_id=str(workspace_id),
        repository_path=repository_path,
        db=db,
    )

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
