import re

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.code_chunk import CodeChunk
from app.services.retrieval.candidates import (
    RetrievalCandidate,
)


MAX_STRUCTURAL_TERMS = 8


def escape_like_query(
    query: str,
) -> str:
    return (
        query.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


def extract_query_terms(
    query: str,
) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()

    for match in re.finditer(
        r"[A-Za-z_][A-Za-z0-9_]*",
        query,
    ):
        term = match.group(0)
        normalized = term.lower()

        if (
            len(normalized) < 2
            or normalized in seen
        ):
            continue

        seen.add(normalized)
        terms.append(term)

    return terms[:MAX_STRUCTURAL_TERMS]


def structural_score(
    chunk: CodeChunk,
    terms: list[str],
) -> int:
    symbol_name = (
        chunk.symbol_name or ""
    ).lower()
    file_path = chunk.file_path.lower()
    score = 0

    for term in terms:
        normalized = term.lower()

        if symbol_name == normalized:
            score = max(
                score,
                100,
            )
        elif normalized in symbol_name:
            score = max(
                score,
                80,
            )

        if normalized in file_path:
            score = max(
                score,
                60,
            )

    return score


async def retrieve_structural(
    db: AsyncSession,
    *,
    workspace_id: str,
    query: str,
    limit: int,
) -> list[RetrievalCandidate]:
    terms = extract_query_terms(
        query.strip()
    )

    if not terms or limit <= 0:
        return []

    conditions = []

    for term in terms:
        pattern = (
            "%"
            + escape_like_query(term)
            + "%"
        )
        conditions.extend(
            [
                CodeChunk.symbol_name.ilike(
                    pattern,
                    escape="\\",
                ),
                CodeChunk.file_path.ilike(
                    pattern,
                    escape="\\",
                ),
            ]
        )

    result = await db.execute(
        select(CodeChunk)
        .where(
            CodeChunk.workspace_id
            == workspace_id,
            CodeChunk.chunk_type
            == "symbol",
            or_(*conditions),
        )
        .limit(limit * 5)
    )

    ranked_chunks = sorted(
        result.scalars().all(),
        key=lambda chunk: (
            -structural_score(
                chunk,
                terms,
            ),
            chunk.file_path,
            chunk.start_line,
            str(chunk.id),
        ),
    )[:limit]

    return [
        RetrievalCandidate(
            chunk_id=chunk.id,
            file_path=chunk.file_path,
            symbol_name=chunk.symbol_name,
            symbol_kind=chunk.symbol_kind,
            start_line=chunk.start_line,
            end_line=chunk.end_line,
            content=chunk.content,
            source="structural",
            rank=index,
            raw_score=float(
                structural_score(
                    chunk,
                    terms,
                )
            ),
        )
        for index, chunk in enumerate(
            ranked_chunks,
            start=1,
        )
    ]
