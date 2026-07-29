from typing import Any

from pydantic import (
    BaseModel,
    Field,
)


class RetrievalBuildFailure(BaseModel):
    file_path: str
    reason: str


class RetrievalBuildResponse(BaseModel):
    workspace_id: str
    files_processed: int
    files_failed: int
    chunks_created: int
    chunks_embedded: int
    chunks_embedding_failed: int
    failures: list[RetrievalBuildFailure]


class RetrievalSearchRequest(BaseModel):
    query: str = Field(
        min_length=1,
        max_length=500,
    )
    top_k: int = Field(
        default=10,
        ge=1,
        le=50,
    )
    debug: bool = False


class RetrievalSearchResult(BaseModel):
    chunk_id: str
    file_path: str
    symbol_name: str | None
    symbol_kind: str | None
    start_line: int
    end_line: int
    content: str
    score: float
    matched_by: list[str]


class ContextChunk(BaseModel):
    chunk_id: str
    symbol: str | None
    kind: str | None
    start_line: int
    end_line: int
    content: str
    score: float
    matched_by: list[str]


class ContextFile(BaseModel):
    path: str
    chunks: list[ContextChunk]


class ContextPack(BaseModel):
    query: str
    estimated_tokens: int
    files: list[ContextFile]


class RetrievalSearchResponse(BaseModel):
    query: str
    results: list[RetrievalSearchResult]
    context: ContextPack
    debug: dict[str, Any] | None = None
