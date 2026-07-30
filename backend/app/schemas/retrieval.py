# Module purpose: Define validated retrieval API payload schemas.

from typing import Any

from pydantic import (
    BaseModel,
    Field,
)


# Purpose: Validate and represent retrieval build failure data.
class RetrievalBuildFailure(BaseModel):
    file_path: str
    reason: str


# Purpose: Validate and represent retrieval build response data.
class RetrievalBuildResponse(BaseModel):
    workspace_id: str
    files_processed: int
    files_failed: int
    chunks_created: int
    chunks_embedded: int
    chunks_embedding_failed: int
    failures: list[RetrievalBuildFailure]


# Purpose: Validate and represent retrieval search request data.
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


# Purpose: Validate and represent retrieval search result data.
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


# Purpose: Validate and represent context chunk data.
class ContextChunk(BaseModel):
    chunk_id: str
    symbol: str | None
    kind: str | None
    start_line: int
    end_line: int
    content: str
    score: float
    matched_by: list[str]


# Purpose: Validate and represent context file data.
class ContextFile(BaseModel):
    path: str
    chunks: list[ContextChunk]


# Purpose: Validate and represent context pack data.
class ContextPack(BaseModel):
    query: str
    estimated_tokens: int
    files: list[ContextFile]


# Purpose: Validate and represent retrieval search response data.
class RetrievalSearchResponse(BaseModel):
    query: str
    results: list[RetrievalSearchResult]
    context: ContextPack
    debug: dict[str, Any] | None = None
