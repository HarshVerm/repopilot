import asyncio
import subprocess
import uuid
from pathlib import Path

from sqlalchemy import delete, func, select

from app.db.models.code_chunk import CodeChunk
from app.db.models.code_index import RepositoryFile
from app.db.session import (
    AsyncSessionLocal,
    engine,
)
from app.services.indexing.indexer import (
    index_repository,
)
from app.services.retrieval.lexical import (
    retrieve_lexical,
)
from app.services.retrieval.semantic import (
    retrieve_semantic,
)
from app.services.retrieval.service import (
    build_retrieval_index,
    hybrid_search,
)
from tests.fakes import FakeEmbeddingClient
from tests.retrieval_fixtures import (
    create_retrieval_fixture_repo,
)


class FailingEmbeddingClient:
    model = "failing-embedding-model"
    dimensions = 1536
    batch_size = 2

    async def embed(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        raise RuntimeError(
            "embedding provider unavailable"
        )


async def delete_workspace(
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


async def count_workspace_chunks(
    workspace_id: str,
) -> int:
    async with AsyncSessionLocal() as db:
        return (
            await db.scalar(
                select(func.count())
                .select_from(CodeChunk)
                .where(
                    CodeChunk.workspace_id
                    == workspace_id
                )
            )
            or 0
        )


async def setup_indexed_fixture(
    workspace_id: str,
    repo: Path,
) -> None:
    create_retrieval_fixture_repo(repo)

    async with AsyncSessionLocal() as db:
        await index_repository(
            workspace_id,
            repo,
            db,
        )
    await dispose_database_engine()


def test_retrieval_build_rebuilds_without_duplicates_and_keeps_other_workspaces(
    tmp_path: Path,
):
    workspace_a = str(uuid.uuid4())
    workspace_b = str(uuid.uuid4())
    repo = tmp_path / "repo"

    async def run_test():
        try:
            await setup_indexed_fixture(
                workspace_a,
                repo,
            )

            async with AsyncSessionLocal() as db:
                first = await build_retrieval_index(
                    workspace_id=workspace_a,
                    repository_path=repo,
                    db=db,
                    embedding_client=FakeEmbeddingClient(),
                )

            first_count = await count_workspace_chunks(
                workspace_a
            )

            async with AsyncSessionLocal() as db:
                file_id = await db.scalar(
                    select(RepositoryFile.id)
                    .where(
                        RepositoryFile.workspace_id
                        == workspace_a
                    )
                    .limit(1)
                )
                db.add(
                    CodeChunk(
                        workspace_id=workspace_a,
                        file_id=file_id,
                        symbol_id=None,
                        chunk_type="file",
                        file_path="stale.ts",
                        language="typescript",
                        symbol_name=None,
                        symbol_kind=None,
                        start_line=1,
                        end_line=1,
                        chunk_index=0,
                        content="stale chunk",
                        content_hash="1" * 64,
                        embedding_model="fake",
                        embedding=None,
                    )
                )
                db.add(
                    CodeChunk(
                        workspace_id=workspace_b,
                        file_id=file_id,
                        symbol_id=None,
                        chunk_type="file",
                        file_path="other.ts",
                        language="typescript",
                        symbol_name=None,
                        symbol_kind=None,
                        start_line=1,
                        end_line=1,
                        chunk_index=0,
                        content="other workspace",
                        content_hash="2" * 64,
                        embedding_model="fake",
                        embedding=None,
                    )
                )
                await db.commit()

            async with AsyncSessionLocal() as db:
                second = await build_retrieval_index(
                    workspace_id=workspace_a,
                    repository_path=repo,
                    db=db,
                    embedding_client=FakeEmbeddingClient(),
                )

            second_count = await count_workspace_chunks(
                workspace_a
            )
            other_count = await count_workspace_chunks(
                workspace_b
            )

            assert first["chunks_created"] == first_count
            assert second["chunks_created"] == second_count
            assert second_count == first_count
            assert other_count == 1
        finally:
            await delete_workspace(
                workspace_a
            )
            await delete_workspace(
                workspace_b
            )
            await dispose_database_engine()

    asyncio.run(run_test())


def test_embedding_build_failure_keeps_lexical_index_available(
    tmp_path: Path,
):
    workspace_id = str(uuid.uuid4())
    repo = tmp_path / "repo"

    async def run_test():
        try:
            await setup_indexed_fixture(
                workspace_id,
                repo,
            )

            async with AsyncSessionLocal() as db:
                build_result = await build_retrieval_index(
                    workspace_id=workspace_id,
                    repository_path=repo,
                    db=db,
                    embedding_client=FailingEmbeddingClient(),
                )

            async with AsyncSessionLocal() as db:
                lexical = await retrieve_lexical(
                    db,
                    workspace_id=workspace_id,
                    query="setTimeout",
                    limit=10,
                )

            assert build_result["chunks_created"] > 0
            assert build_result["chunks_embedded"] == 0
            assert (
                build_result["chunks_embedding_failed"]
                == build_result["chunks_created"]
            )
            assert any(
                candidate.file_path
                == "src/utils/debounce.ts"
                for candidate in lexical
            )
        finally:
            await delete_workspace(
                workspace_id
            )
            await dispose_database_engine()

    asyncio.run(run_test())


def test_plain_text_repository_content_is_retrievable(
    tmp_path: Path,
):
    workspace_id = str(uuid.uuid4())
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "age.txt").write_text(
        "The configured age value is twenty two.\n",
        encoding="utf-8",
    )
    subprocess.run(
        [
            "git",
            "init",
            "-q",
        ],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        [
            "git",
            "add",
            ".",
        ],
        cwd=repo,
        check=True,
    )

    async def run_test():
        try:
            async with AsyncSessionLocal() as db:
                index_result = await index_repository(
                    workspace_id,
                    repo,
                    db,
                )
                build_result = await build_retrieval_index(
                    workspace_id=workspace_id,
                    repository_path=repo,
                    db=db,
                    embedding_client=FakeEmbeddingClient(),
                )

            async with AsyncSessionLocal() as db:
                lexical = await retrieve_lexical(
                    db,
                    workspace_id=workspace_id,
                    query="configured age value",
                    limit=10,
                )

            assert index_result["files_indexed"] == 1
            assert build_result["chunks_created"] == 1
            assert any(
                candidate.file_path == "age.txt"
                for candidate in lexical
            )
        finally:
            await delete_workspace(
                workspace_id
            )
            await dispose_database_engine()

    asyncio.run(run_test())


def test_lexical_and_semantic_retrieval_are_workspace_scoped(
    tmp_path: Path,
):
    workspace_a = str(uuid.uuid4())
    workspace_b = str(uuid.uuid4())
    repo = tmp_path / "repo"

    async def run_test():
        try:
            await setup_indexed_fixture(
                workspace_a,
                repo,
            )

            async with AsyncSessionLocal() as db:
                await build_retrieval_index(
                    workspace_id=workspace_a,
                    repository_path=repo,
                    db=db,
                    embedding_client=FakeEmbeddingClient(),
                )

            async with AsyncSessionLocal() as db:
                file_id = await db.scalar(
                    select(RepositoryFile.id)
                    .where(
                        RepositoryFile.workspace_id
                        == workspace_a
                    )
                    .limit(1)
                )
                db.add(
                    CodeChunk(
                        workspace_id=workspace_b,
                        file_id=file_id,
                        symbol_id=None,
                        chunk_type="file",
                        file_path="private/debounce.ts",
                        language="typescript",
                        symbol_name=None,
                        symbol_kind=None,
                        start_line=1,
                        end_line=1,
                        chunk_index=0,
                        content="private debounce setTimeout",
                        content_hash="3" * 64,
                        embedding_model="fake",
                        embedding=FakeEmbeddingClient()
                        .dimensions
                        * [0.001],
                    )
                )
                await db.commit()

            async with AsyncSessionLocal() as db:
                lexical = await retrieve_lexical(
                    db,
                    workspace_id=workspace_a,
                    query="setTimeout",
                    limit=10,
                )
                semantic = await retrieve_semantic(
                    db,
                    workspace_id=workspace_a,
                    query="wait before calling search API",
                    limit=10,
                    embedding_client=FakeEmbeddingClient(),
                )

            assert lexical
            assert semantic
            assert all(
                not candidate.file_path.startswith(
                    "private/"
                )
                for candidate in lexical + semantic
            )
            assert any(
                candidate.file_path
                == "src/utils/debounce.ts"
                for candidate in lexical
            )
        finally:
            await delete_workspace(
                workspace_a
            )
            await delete_workspace(
                workspace_b
            )
            await dispose_database_engine()

    asyncio.run(run_test())


def test_hybrid_search_returns_relevant_context_for_issue_query(
    tmp_path: Path,
):
    workspace_id = str(uuid.uuid4())
    repo = tmp_path / "repo"

    async def run_test():
        try:
            await setup_indexed_fixture(
                workspace_id,
                repo,
            )

            async with AsyncSessionLocal() as db:
                build_result = await build_retrieval_index(
                    workspace_id=workspace_id,
                    repository_path=repo,
                    db=db,
                    embedding_client=FakeEmbeddingClient(),
                )

            async with AsyncSessionLocal() as db:
                exact = await hybrid_search(
                    workspace_id=workspace_id,
                    query="debounce",
                    top_k=10,
                    db=db,
                    embedding_client=FakeEmbeddingClient(),
                    debug=True,
                )
                issue = await hybrid_search(
                    workspace_id=workspace_id,
                    query=(
                        "Search request fires for every keypress. "
                        "Wait briefly before calling the API."
                    ),
                    top_k=10,
                    db=db,
                    embedding_client=FakeEmbeddingClient(),
                    debug=True,
                )

            exact_paths = {
                result["file_path"]
                for result in exact["results"][:5]
            }
            issue_paths = [
                result["file_path"]
                for result in issue["results"]
            ]
            context_paths = {
                file["path"]
                for file in issue["context"]["files"]
            }

            assert build_result["chunks_created"] > 0
            assert build_result["chunks_embedded"] == build_result[
                "chunks_created"
            ]
            assert {
                "src/utils/debounce.ts",
                "src/hooks/useDebounce.ts",
            }.issubset(exact_paths)
            assert {
                "src/hooks/useDebounce.ts",
                "src/utils/debounce.ts",
                "src/components/SearchBox.tsx",
                "src/api/searchApi.ts",
            }.issubset(set(issue_paths))
            assert {
                "src/hooks/useDebounce.ts",
                "src/utils/debounce.ts",
                "src/components/SearchBox.tsx",
            }.issubset(context_paths)
            assert issue["debug"]["semantic_available"] is True
            assert all(
                result["matched_by"]
                for result in issue["results"]
            )
        finally:
            await delete_workspace(
                workspace_id
            )
            await dispose_database_engine()

    asyncio.run(run_test())
