import asyncio
import hashlib
import subprocess
import uuid
from pathlib import Path

import pytest
from sqlalchemy import delete, func, select

from app.db.models.code_index import (
    CodeSymbol,
    RepositoryFile,
)
from app.db.session import (
    AsyncSessionLocal,
    engine,
)
from app.services.indexing import indexer
from app.services.indexing.indexer import (
    index_repository,
)
from app.services.indexing.scanner import SourceFile


def init_git_repo(
    repo_path: Path,
) -> None:
    subprocess.run(
        ["git", "init", "-q"],
        cwd=repo_path,
        check=True,
    )
    subprocess.run(
        ["git", "add", "."],
        cwd=repo_path,
        check=True,
    )


def write_file(
    repo_path: Path,
    relative_path: str,
    content: bytes,
) -> None:
    path = repo_path / relative_path
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    path.write_bytes(content)


async def delete_workspace_index(
    workspace_id: str,
) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(
            delete(RepositoryFile).where(
                RepositoryFile.workspace_id
                == workspace_id
            )
        )
        await db.commit()


async def dispose_database_engine() -> None:
    await engine.dispose()


async def list_workspace_symbols(
    workspace_id: str,
) -> set[str]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(CodeSymbol.name)
            .join(
                RepositoryFile,
                CodeSymbol.file_id
                == RepositoryFile.id,
            )
            .where(
                RepositoryFile.workspace_id
                == workspace_id
            )
        )

        return {
            row.name
            for row in result.all()
        }


async def workspace_counts(
    workspace_id: str,
) -> tuple[int, int]:
    async with AsyncSessionLocal() as db:
        file_count = await db.scalar(
            select(func.count())
            .select_from(RepositoryFile)
            .where(
                RepositoryFile.workspace_id
                == workspace_id
            )
        )
        symbol_count = await db.scalar(
            select(func.count())
            .select_from(CodeSymbol)
            .join(
                RepositoryFile,
                CodeSymbol.file_id
                == RepositoryFile.id,
            )
            .where(
                RepositoryFile.workspace_id
                == workspace_id
            )
        )

        return (
            file_count or 0,
            symbol_count or 0,
        )


async def workspace_file_hash(
    workspace_id: str,
    file_path: str,
) -> str | None:
    async with AsyncSessionLocal() as db:
        return await db.scalar(
            select(RepositoryFile.sha256)
            .where(
                RepositoryFile.workspace_id
                == workspace_id,
                RepositoryFile.file_path
                == file_path,
            )
        )


def test_index_repository_replaces_existing_index(
    tmp_path: Path,
):
    workspace_id = str(uuid.uuid4())
    repo = tmp_path / "repo"
    repo.mkdir()
    write_file(
        repo,
        "src/search.py",
        b"def old_symbol():\n    pass\n",
    )
    init_git_repo(repo)

    async def run_test():
        try:
            async with AsyncSessionLocal() as db:
                first_result = await index_repository(
                    workspace_id,
                    repo,
                    db,
                )

            write_file(
                repo,
                "src/search.py",
                b"def new_symbol():\n    pass\n",
            )
            subprocess.run(
                ["git", "add", "."],
                cwd=repo,
                check=True,
            )

            async with AsyncSessionLocal() as db:
                second_result = await index_repository(
                    workspace_id,
                    repo,
                    db,
                )

            symbols = await list_workspace_symbols(
                workspace_id
            )
            counts = await workspace_counts(
                workspace_id
            )
            stored_hash = await workspace_file_hash(
                workspace_id,
                "src/search.py",
            )

            assert first_result["files_indexed"] == 1
            assert second_result["files_indexed"] == 1
            assert "old_symbol" not in symbols
            assert "new_symbol" in symbols
            assert counts == (1, 1)
            assert stored_hash == hashlib.sha256(
                b"def new_symbol():\n    pass\n"
            ).hexdigest()
        finally:
            await delete_workspace_index(
                workspace_id
            )
            await dispose_database_engine()

    asyncio.run(run_test())


def test_index_repository_indexes_plain_text_without_ast_symbols(
    tmp_path: Path,
):
    workspace_id = str(uuid.uuid4())
    repo = tmp_path / "repo"
    repo.mkdir()
    content = b"RepoPilot should use this text as repository context.\n"
    write_file(
        repo,
        "notes.txt",
        content,
    )
    init_git_repo(repo)

    async def run_test():
        try:
            async with AsyncSessionLocal() as db:
                result = await index_repository(
                    workspace_id,
                    repo,
                    db,
                )

            counts = await workspace_counts(
                workspace_id
            )
            stored_hash = await workspace_file_hash(
                workspace_id,
                "notes.txt",
            )

            assert result["files_discovered"] == 1
            assert result["files_indexed"] == 1
            assert result["files_failed"] == 0
            assert result["symbols_indexed"] == 0
            assert counts == (1, 0)
            assert stored_hash == hashlib.sha256(
                content
            ).hexdigest()
        finally:
            await delete_workspace_index(
                workspace_id
            )
            await dispose_database_engine()

    asyncio.run(run_test())


def test_index_repository_continues_after_file_parse_failure(
    tmp_path: Path,
    monkeypatch,
):
    workspace_id = str(uuid.uuid4())
    repo = tmp_path / "repo"
    repo.mkdir()
    write_file(
        repo,
        "src/good.py",
        b"def good_symbol():\n    pass\n",
    )
    write_file(
        repo,
        "src/bad.ts",
        b"export function broken() {}\n",
    )
    init_git_repo(repo)

    original_parse_source = indexer.parse_source

    def fake_parse_source(
        language_name: str,
        source: bytes,
    ):
        if b"broken" in source:
            raise ValueError(
                "forced parser failure"
            )

        return original_parse_source(
            language_name,
            source,
        )

    monkeypatch.setattr(
        indexer,
        "parse_source",
        fake_parse_source,
    )

    async def run_test():
        try:
            async with AsyncSessionLocal() as db:
                result = await index_repository(
                    workspace_id,
                    repo,
                    db,
                )

            symbols = await list_workspace_symbols(
                workspace_id
            )
            counts = await workspace_counts(
                workspace_id
            )

            assert result["files_discovered"] == 2
            assert result["files_indexed"] == 1
            assert result["files_failed"] == 1
            assert result["symbols_indexed"] == 1
            assert result["failures"] == [
                {
                    "file_path": "src/bad.ts",
                    "reason": "source file could not be parsed",
                }
            ]
            assert symbols == {
                "good_symbol"
            }
            assert counts == (1, 1)
        finally:
            await delete_workspace_index(
                workspace_id
            )
            await dispose_database_engine()

    asyncio.run(run_test())


def test_index_repository_continues_after_file_read_failure(
    tmp_path: Path,
    monkeypatch,
):
    workspace_id = str(uuid.uuid4())
    good_file = tmp_path / "good.py"
    good_file.write_bytes(
        b"def good_symbol():\n    pass\n"
    )

    class UnreadablePath:
        def read_bytes(self):
            raise OSError(
                "permission denied"
            )

    monkeypatch.setattr(
        indexer,
        "scan_repository",
        lambda repository_path: [
            SourceFile(
                relative_path="good.py",
                absolute_path=good_file,
                language="python",
                size_bytes=good_file.stat().st_size,
            ),
            SourceFile(
                relative_path="bad.py",
                absolute_path=UnreadablePath(),
                language="python",
                size_bytes=10,
            ),
        ],
    )

    async def run_test():
        try:
            async with AsyncSessionLocal() as db:
                result = await index_repository(
                    workspace_id,
                    tmp_path,
                    db,
                )

            symbols = await list_workspace_symbols(
                workspace_id
            )

            assert result["files_discovered"] == 2
            assert result["files_indexed"] == 1
            assert result["files_failed"] == 1
            assert result["failures"] == [
                {
                    "file_path": "bad.py",
                    "reason": "source file could not be read",
                }
            ]
            assert symbols == {
                "good_symbol"
            }
        finally:
            await delete_workspace_index(
                workspace_id
            )
            await dispose_database_engine()

    asyncio.run(run_test())


def test_index_repository_does_not_swallow_database_errors(
    tmp_path: Path,
):
    repo = tmp_path / "repo"
    repo.mkdir()
    write_file(
        repo,
        "src/search.py",
        b"def search():\n    pass\n",
    )
    init_git_repo(repo)

    class FailingDatabase:
        async def execute(self, *args, **kwargs):
            raise RuntimeError(
                "database unavailable"
            )

    async def run_test():
        with pytest.raises(
            RuntimeError,
            match="database unavailable",
        ):
            await index_repository(
                str(uuid.uuid4()),
                repo,
                FailingDatabase(),
            )

    asyncio.run(run_test())
