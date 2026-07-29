import uuid
from pathlib import Path

import pytest

from app.db.models.code_index import (
    CodeSymbol,
    RepositoryFile,
)
from app.services.chunking.chunker import (
    UnsafeRepositoryPathError,
    build_code_chunks_for_file,
    resolve_safe_repository_file,
)
from app.services.chunking.tokenizer import (
    count_tokens,
)


def make_file_record(
    file_path: str,
) -> RepositoryFile:
    return RepositoryFile(
        id=uuid.uuid4(),
        workspace_id=str(uuid.uuid4()),
        file_path=file_path,
        language="typescript",
        size_bytes=100,
        sha256="0" * 64,
    )


def make_symbol(
    *,
    name: str,
    kind: str,
    start_line: int,
    end_line: int,
) -> CodeSymbol:
    return CodeSymbol(
        id=uuid.uuid4(),
        file_id=uuid.uuid4(),
        name=name,
        kind=kind,
        start_line=start_line,
        end_line=end_line,
    )


def test_build_code_chunks_for_symbols_and_file_fallback(
    tmp_path: Path,
):
    repo = tmp_path / "repo"
    repo.mkdir()
    source_path = repo / "src/example.ts"
    source_path.parent.mkdir()
    source_path.write_text(
        """const DEFAULT_DELAY = 300;

export function debounce() {
  return DEFAULT_DELAY;
}

export class SearchService {
  search() {
    return debounce();
  }
}
""",
        encoding="utf-8",
    )

    file_record = make_file_record(
        "src/example.ts"
    )
    file_record.symbols = [
        make_symbol(
            name="debounce",
            kind="function",
            start_line=3,
            end_line=5,
        ),
        make_symbol(
            name="SearchService",
            kind="class",
            start_line=7,
            end_line=11,
        ),
        make_symbol(
            name="search",
            kind="method",
            start_line=8,
            end_line=10,
        ),
        make_symbol(
            name='import "x"',
            kind="import",
            start_line=1,
            end_line=1,
        ),
    ]

    chunks = build_code_chunks_for_file(
        file_record,
        repo,
        max_tokens=100,
        overlap_tokens=10,
    )
    symbol_chunks = [
        chunk
        for chunk in chunks
        if chunk.chunk_type == "symbol"
    ]
    file_chunks = [
        chunk
        for chunk in chunks
        if chunk.chunk_type == "file"
    ]

    assert {
        chunk.symbol_name
        for chunk in symbol_chunks
    } == {
        "debounce",
        "SearchService",
        "search",
    }
    assert file_chunks
    assert "DEFAULT_DELAY" in file_chunks[0].content
    assert all(
        chunk.content_hash
        for chunk in chunks
    )
    assert all(
        not Path(chunk.file_path).is_absolute()
        for chunk in chunks
    )


def test_oversized_symbol_and_file_chunks_are_split(
    tmp_path: Path,
):
    repo = tmp_path / "repo"
    repo.mkdir()
    repeated_lines = "\n".join(
        f"  const value{i} = '{'x' * 40}';"
        for i in range(80)
    )
    source = (
        "export function bigSearch() {\n"
        f"{repeated_lines}\n"
        "  return value0;\n"
        "}\n"
    )
    source_path = repo / "src/big.ts"
    source_path.parent.mkdir()
    source_path.write_text(
        source,
        encoding="utf-8",
    )

    file_record = make_file_record(
        "src/big.ts"
    )
    file_record.symbols = [
        make_symbol(
            name="bigSearch",
            kind="function",
            start_line=1,
            end_line=83,
        )
    ]

    chunks = build_code_chunks_for_file(
        file_record,
        repo,
        max_tokens=80,
        overlap_tokens=10,
    )
    big_search_chunks = [
        chunk
        for chunk in chunks
        if chunk.symbol_name == "bigSearch"
    ]
    file_chunks = [
        chunk
        for chunk in chunks
        if chunk.chunk_type == "file"
    ]

    assert len(big_search_chunks) > 1
    assert len(file_chunks) > 1
    assert [
        chunk.chunk_index
        for chunk in big_search_chunks
    ] == list(range(len(big_search_chunks)))
    assert all(
        count_tokens(chunk.content) <= 80
        for chunk in chunks
    )


def test_safe_file_resolution_rejects_symlink_escape(
    tmp_path: Path,
):
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "secret.py"
    outside.write_text(
        "SECRET = True\n",
        encoding="utf-8",
    )
    link = repo / "escape.py"
    link.symlink_to(outside)

    with pytest.raises(
        UnsafeRepositoryPathError
    ):
        resolve_safe_repository_file(
            repo,
            "escape.py",
        )

    with pytest.raises(
        UnsafeRepositoryPathError
    ):
        resolve_safe_repository_file(
            repo,
            "../secret.py",
        )
