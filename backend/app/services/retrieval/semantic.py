"""Retrieve conceptually similar chunks with pgvector cosine distance."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.code_chunk import CodeChunk
from app.services.embeddings.client import (
    EmbeddingClient,
    validate_embedding_dimensions,
)
from app.services.retrieval.candidates import (
    RetrievalCandidate,
)


async def retrieve_semantic(
    db: AsyncSession,
    *,
    workspace_id: str,
    query: str,
    limit: int,
    embedding_client: EmbeddingClient,
) -> list[RetrievalCandidate]:
    """Embed the issue query and return its nearest workspace code chunks."""
    stripped_query = query.strip()

    if not stripped_query or limit <= 0:
        return []

    query_embedding = (
        await embedding_client.embed(
            [stripped_query]
        )
    )[0]
    validate_embedding_dimensions(
        query_embedding,
        settings.embedding_dimensions,
    )

    distance_expression = (
        CodeChunk.embedding.cosine_distance(
            query_embedding
        ).label("distance")
    )

    result = await db.execute(
        select(
            CodeChunk,
            distance_expression,
        )
        .where(
            CodeChunk.workspace_id
            == workspace_id,
            CodeChunk.embedding.is_not(None),
        )
        .order_by(
            distance_expression,
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
            source="semantic",
            rank=index,
            raw_score=float(distance or 0),
        )
        for index, (
            chunk,
            distance,
        ) in enumerate(result.all(), start=1)
    ]
