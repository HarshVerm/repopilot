# Module purpose: Define validated indexing API payload schemas.

from pydantic import BaseModel


# Purpose: Validate and represent index failure response data.
class IndexFailureResponse(BaseModel):
    file_path: str
    reason: str


# Purpose: Validate and represent index response data.
class IndexResponse(BaseModel):
    workspace_id: str
    files_discovered: int
    files_indexed: int
    files_failed: int
    symbols_indexed: int
    failures: list[IndexFailureResponse]


# Purpose: Validate and represent symbol search result data.
class SymbolSearchResult(BaseModel):
    name: str
    kind: str
    file_path: str
    language: str
    start_line: int
    end_line: int
