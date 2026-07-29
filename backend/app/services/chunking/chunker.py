import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
from app.db.models.code_index import (
    CodeSymbol,
    RepositoryFile,
)
from app.services.chunking.tokenizer import (
    split_text_by_token_budget,
)
from app.services.indexing.scanner import (
    is_relative_to,
)


SYMBOL_CHUNK_KINDS = {
    "class",
    "function",
    "method",
}


class UnsafeRepositoryPathError(ValueError):
    pass


@dataclass(frozen=True)
class ChunkDraft:
    file_id: uuid.UUID
    symbol_id: uuid.UUID | None
    chunk_type: str
    file_path: str
    language: str
    symbol_name: str | None
    symbol_kind: str | None
    start_line: int
    end_line: int
    chunk_index: int
    content: str
    content_hash: str


def build_embedding_text(
    chunk: ChunkDraft,
) -> str:
    metadata = [
        f"File: {chunk.file_path}",
        f"Language: {chunk.language}",
        f"Lines: {chunk.start_line}-{chunk.end_line}",
    ]

    if chunk.symbol_name:
        metadata.append(
            f"Symbol: {chunk.symbol_name}"
        )

    if chunk.symbol_kind:
        metadata.append(
            f"Kind: {chunk.symbol_kind}"
        )

    return (
        "\n".join(metadata)
        + "\n\n"
        + chunk.content
    )


def calculate_chunk_hash(
    chunk: ChunkDraft,
) -> str:
    return hashlib.sha256(
        build_embedding_text(chunk).encode(
            "utf-8"
        )
    ).hexdigest()


def resolve_safe_repository_file(
    repository_path: Path,
    file_path: str,
) -> Path:
    repository_root = repository_path.resolve()
    relative_path = Path(file_path)

    if (
        relative_path.is_absolute()
        or ".." in relative_path.parts
    ):
        raise UnsafeRepositoryPathError(
            "repository file path is not relative"
        )

    candidate_path = (
        repository_root / relative_path
    )

    if candidate_path.is_symlink():
        raise UnsafeRepositoryPathError(
            "repository file path is a symlink"
        )

    try:
        resolved_path = candidate_path.resolve(
            strict=True
        )
    except OSError as exc:
        raise UnsafeRepositoryPathError(
            "repository file path cannot be resolved"
        ) from exc

    if not is_relative_to(
        resolved_path,
        repository_root,
    ):
        raise UnsafeRepositoryPathError(
            "repository file path escapes workspace"
        )

    if not resolved_path.is_file():
        raise UnsafeRepositoryPathError(
            "repository file path is not a file"
        )

    return resolved_path


def read_repository_source(
    repository_path: Path,
    file_path: str,
) -> str:
    resolved_path = resolve_safe_repository_file(
        repository_path,
        file_path,
    )

    return resolved_path.read_bytes().decode(
        "utf-8",
        errors="ignore",
    )


def slice_lines(
    source: str,
    start_line: int,
    end_line: int,
) -> str:
    lines = source.splitlines(
        keepends=True
    )

    if not lines:
        return ""

    safe_start = max(
        1,
        start_line,
    )
    safe_end = min(
        len(lines),
        end_line,
    )

    if safe_start > safe_end:
        return ""

    return "".join(
        lines[
            safe_start - 1 : safe_end
        ]
    )


def make_chunk_draft(
    *,
    file_record: RepositoryFile,
    symbol: CodeSymbol | None,
    chunk_type: str,
    start_line: int,
    end_line: int,
    chunk_index: int,
    content: str,
) -> ChunkDraft:
    draft = ChunkDraft(
        file_id=file_record.id,
        symbol_id=(
            symbol.id
            if symbol is not None
            else None
        ),
        chunk_type=chunk_type,
        file_path=file_record.file_path,
        language=file_record.language,
        symbol_name=(
            symbol.name
            if symbol is not None
            else None
        ),
        symbol_kind=(
            symbol.kind
            if symbol is not None
            else None
        ),
        start_line=start_line,
        end_line=end_line,
        chunk_index=chunk_index,
        content=content,
        content_hash="",
    )

    return ChunkDraft(
        **{
            **draft.__dict__,
            "content_hash": calculate_chunk_hash(
                draft
            ),
        }
    )


def build_symbol_chunks(
    file_record: RepositoryFile,
    symbol: CodeSymbol,
    source: str,
    max_tokens: int,
    overlap_tokens: int,
) -> list[ChunkDraft]:
    if symbol.kind not in SYMBOL_CHUNK_KINDS:
        return []

    symbol_source = slice_lines(
        source,
        symbol.start_line,
        symbol.end_line,
    )

    if not symbol_source.strip():
        return []

    splits = split_text_by_token_budget(
        symbol_source,
        max_tokens=max_tokens,
        overlap_tokens=overlap_tokens,
        start_line=symbol.start_line,
    )

    return [
        make_chunk_draft(
            file_record=file_record,
            symbol=symbol,
            chunk_type="symbol",
            start_line=split.start_line,
            end_line=split.end_line,
            chunk_index=index,
            content=split.content,
        )
        for index, split in enumerate(splits)
        if split.content.strip()
    ]


def build_file_fallback_chunks(
    file_record: RepositoryFile,
    source: str,
    max_tokens: int,
    overlap_tokens: int,
) -> list[ChunkDraft]:
    splits = split_text_by_token_budget(
        source,
        max_tokens=max_tokens,
        overlap_tokens=overlap_tokens,
        start_line=1,
    )

    return [
        make_chunk_draft(
            file_record=file_record,
            symbol=None,
            chunk_type="file",
            start_line=split.start_line,
            end_line=split.end_line,
            chunk_index=index,
            content=split.content,
        )
        for index, split in enumerate(splits)
        if split.content.strip()
    ]


def build_code_chunks_for_file(
    file_record: RepositoryFile,
    repository_path: Path,
    max_tokens: int = settings.max_chunk_tokens,
    overlap_tokens: int = settings.chunk_overlap_tokens,
) -> list[ChunkDraft]:
    source = read_repository_source(
        repository_path,
        file_record.file_path,
    )
    symbols = sorted(
        file_record.symbols,
        key=lambda symbol: (
            symbol.start_line,
            symbol.end_line,
            symbol.name,
        ),
    )

    chunks: list[ChunkDraft] = []

    for symbol in symbols:
        chunks.extend(
            build_symbol_chunks(
                file_record=file_record,
                symbol=symbol,
                source=source,
                max_tokens=max_tokens,
                overlap_tokens=overlap_tokens,
            )
        )

    chunks.extend(
        build_file_fallback_chunks(
            file_record=file_record,
            source=source,
            max_tokens=max_tokens,
            overlap_tokens=overlap_tokens,
        )
    )

    return chunks
