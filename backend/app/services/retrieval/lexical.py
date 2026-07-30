"""Retrieve exact textual matches with PostgreSQL full-text search."""

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.code_chunk import CodeChunk
from app.services.retrieval.candidates import (
    RetrievalCandidate,
)


async def retrieve_lexical(
    db: AsyncSession,
    *,
    workspace_id: str,
    query: str,
    limit: int,
) -> list[RetrievalCandidate]:
    """Rank workspace chunks using their weighted PostgreSQL search vector."""
    stripped_query = query.strip()

    if not stripped_query or limit <= 0:
        return []

    text_query = func.websearch_to_tsquery(
        "simple",
        stripped_query,
    )
    rank_expression = func.ts_rank_cd(
        CodeChunk.search_vector,
        text_query,
    ).label("rank_score")

    result = await db.execute(
        select(
            CodeChunk,
            rank_expression,
        )
        .where(
            CodeChunk.workspace_id
            == workspace_id,
            CodeChunk.search_vector.op("@@")(
                text_query
            ),
        )
        .order_by(
            desc(rank_expression),
            CodeChunk.file_path,
            CodeChunk.start_line,
            CodeChunk.chunk_index,
        )
        .limit(limit)
    )

    return [
        RetrievalCandidate(
            chunk_id=chunk.id,
            file_path=chunk.file_path,
            symbol_name=chunk.symbol_name,
            symbol_kind=chunk.symbol_kind,
            start_line=chunk.start_line,
            end_line=chunk.end_line,
            content=chunk.content,
            source="lexical",
            rank=index,
            raw_score=float(rank_score or 0),
        )
        for index, (
            chunk,
            rank_score,
        ) in enumerate(result.all(), start=1)
    ]
