"""Define the common candidate shape shared by all RAG retrievers."""

import uuid
from dataclasses import dataclass
from typing import Literal


RetrieverName = Literal[
    "structural",
    "lexical",
    "semantic",
]


RETRIEVER_ORDER = {
    "structural": 0,
    "lexical": 1,
    "semantic": 2,
}


@dataclass(frozen=True)
class RetrievalCandidate:
    """Represent one ranked code chunk before or after result fusion."""

    chunk_id: uuid.UUID
    file_path: str
    symbol_name: str | None
    symbol_kind: str | None
    start_line: int
    end_line: int
    content: str
    source: RetrieverName
    rank: int
    raw_score: float | None = None
    score: float = 0.0
    matched_by: tuple[RetrieverName, ...] = ()


def ordered_sources(
    sources: set[RetrieverName],
) -> tuple[RetrieverName, ...]:
    """Return matching retriever names in deterministic display order."""
    return tuple(
        sorted(
            sources,
            key=lambda source: RETRIEVER_ORDER[
                source
            ],
        )
    )
