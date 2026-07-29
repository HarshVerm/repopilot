from pydantic import BaseModel


class IndexFailureResponse(BaseModel):
    file_path: str
    reason: str


class IndexResponse(BaseModel):
    workspace_id: str
    files_discovered: int
    files_indexed: int
    files_failed: int
    symbols_indexed: int
    failures: list[IndexFailureResponse]


class SymbolSearchResult(BaseModel):
    name: str
    kind: str
    file_path: str
    language: str
    start_line: int
    end_line: int
