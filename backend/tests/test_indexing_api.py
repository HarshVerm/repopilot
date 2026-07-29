import asyncio
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.api.routes.indexing import WORKSPACES_DIR
from app.core.config import settings
from app.db.models.code_index import (
    CodeSymbol,
    RepositoryFile,
)
from app.db.session import get_db
from app.main import app


test_engine = create_async_engine(
    settings.database_url,
    poolclass=NullPool,
)

TestAsyncSessionLocal = async_sessionmaker(
    bind=test_engine,
    expire_on_commit=False,
)


async def override_get_db():
    async with TestAsyncSessionLocal() as session:
        yield session


@pytest.fixture(autouse=True)
def use_test_database_dependency():
    app.dependency_overrides[get_db] = override_get_db

    yield

    app.dependency_overrides.pop(
        get_db,
        None,
    )


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
    async with TestAsyncSessionLocal() as db:
        await db.execute(
            delete(RepositoryFile).where(
                RepositoryFile.workspace_id
                == workspace_id
            )
        )
        await db.commit()


async def dispose_database_engine() -> None:
    await test_engine.dispose()


async def seed_symbols(
    workspace_id: str,
    symbols: list[tuple[str, str, str, str]],
) -> None:
    async with TestAsyncSessionLocal() as db:
        await db.execute(
            delete(RepositoryFile).where(
                RepositoryFile.workspace_id
                == workspace_id
            )
        )

        files_by_path: dict[str, RepositoryFile] = {}

        for name, kind, file_path, language in symbols:
            file_record = files_by_path.get(
                file_path
            )

            if file_record is None:
                file_record = RepositoryFile(
                    workspace_id=workspace_id,
                    file_path=file_path,
                    language=language,
                    size_bytes=42,
                    sha256="0" * 64,
                )
                db.add(file_record)
                await db.flush()
                files_by_path[file_path] = file_record

            db.add(
                CodeSymbol(
                    file_id=file_record.id,
                    name=name,
                    kind=kind,
                    start_line=1,
                    end_line=3,
                )
            )

        await db.commit()


def test_symbol_search_api_matches_and_isolates_workspaces():
    workspace_a = str(uuid.uuid4())
    workspace_b = str(uuid.uuid4())

    async def run_setup():
        await seed_symbols(
            workspace_a,
            [
                (
                    "debounce",
                    "function",
                    "src/utils/debounce.ts",
                    "typescript",
                ),
                (
                    "SearchService",
                    "class",
                    "src/services/SearchService.ts",
                    "typescript",
                ),
                (
                    "SearchBox",
                    "function",
                    "src/components/SearchBox.tsx",
                    "tsx",
                ),
                (
                    "LimitOne",
                    "function",
                    "src/limit/one.ts",
                    "typescript",
                ),
                (
                    "LimitTwo",
                    "function",
                    "src/limit/two.ts",
                    "typescript",
                ),
                (
                    "LimitThree",
                    "function",
                    "src/limit/three.ts",
                    "typescript",
                ),
            ],
        )
        await seed_symbols(
            workspace_b,
            [
                (
                    "debounce",
                    "function",
                    "private/debounce.ts",
                    "typescript",
                )
            ],
        )

    async def run_cleanup():
        await delete_workspace_index(
            workspace_a
        )
        await delete_workspace_index(
            workspace_b
        )

    try:
        asyncio.run(run_setup())
        asyncio.run(dispose_database_engine())

        with TestClient(app) as test_client:
            exact = test_client.get(
                f"/api/v1/index/{workspace_a}/symbols",
                params={"q": "debounce"},
            )
            partial = test_client.get(
                f"/api/v1/index/{workspace_a}/symbols",
                params={"q": "Service"},
            )
            case_insensitive = test_client.get(
                f"/api/v1/index/{workspace_a}/symbols",
                params={"q": "searchbox"},
            )
            unknown = test_client.get(
                f"/api/v1/index/{workspace_a}/symbols",
                params={"q": "missing"},
            )
            limited = test_client.get(
                f"/api/v1/index/{workspace_a}/symbols",
                params={
                    "q": "Limit",
                    "limit": "2",
                },
            )

        assert exact.status_code == 200
        assert exact.json() == [
            {
                "name": "debounce",
                "kind": "function",
                "file_path": "src/utils/debounce.ts",
                "language": "typescript",
                "start_line": 1,
                "end_line": 3,
            }
        ]
        assert partial.status_code == 200
        assert partial.json()[0]["name"] == "SearchService"
        assert case_insensitive.status_code == 200
        assert case_insensitive.json()[0]["name"] == "SearchBox"
        assert unknown.status_code == 200
        assert unknown.json() == []
        assert limited.status_code == 200
        assert len(limited.json()) == 2
    finally:
        asyncio.run(dispose_database_engine())
        asyncio.run(run_cleanup())
        asyncio.run(dispose_database_engine())


def test_symbol_search_api_validation():
    with TestClient(app) as test_client:
        invalid_uuid = test_client.get(
            "/api/v1/index/not-a-uuid/symbols",
            params={"q": "debounce"},
        )
        blank_query = test_client.get(
            f"/api/v1/index/{uuid.uuid4()}/symbols",
            params={"q": "   "},
        )
        invalid_limit = test_client.get(
            f"/api/v1/index/{uuid.uuid4()}/symbols",
            params={
                "q": "debounce",
                "limit": "99",
            },
        )

    assert invalid_uuid.status_code == 422
    assert blank_query.status_code == 422
    assert invalid_limit.status_code == 422


def test_index_and_symbol_search_end_to_end_api():
    workspace_id = str(uuid.uuid4())
    workspace_path = (
        WORKSPACES_DIR / workspace_id
    )
    repo = workspace_path / "repository"
    repo.mkdir(
        parents=True
    )

    write_file(
        repo,
        "src/utils/debounce.ts",
        b"""export function debounce(fn, delay) {
return fn;
}
""",
    )
    write_file(
        repo,
        "src/services/SearchService.ts",
        b"""export class SearchService {
search(query: string) {
return query;
}
}
""",
    )
    write_file(
        repo,
        "src/components/SearchBox.tsx",
        b"""export function SearchBox() {
return <input />;
}
""",
    )
    write_file(
        repo,
        "backend/search.py",
        b"""def search_items(query):
    pass

class SearchIndex:
    pass
""",
    )
    write_file(
        repo,
        "dist/generated.js",
        b"function generated() {}\n",
    )
    write_file(
        repo,
        "node_modules/example/index.js",
        b"function dependency() {}\n",
    )
    init_git_repo(repo)

    try:
        with TestClient(app) as test_client:
            response = test_client.post(
                f"/api/v1/index/{workspace_id}"
            )

            assert response.status_code == 200
            assert response.json()["files_discovered"] == 4
            assert response.json()["files_indexed"] == 4
            assert response.json()["files_failed"] == 0

            expected = {
                "debounce": "src/utils/debounce.ts",
                "SearchService": "src/services/SearchService.ts",
                "SearchBox": "src/components/SearchBox.tsx",
                "search_items": "backend/search.py",
                "SearchIndex": "backend/search.py",
            }

            for symbol_name, file_path in expected.items():
                search_response = test_client.get(
                    f"/api/v1/index/{workspace_id}/symbols",
                    params={"q": symbol_name},
                )

                assert search_response.status_code == 200
                assert search_response.json()[0]["name"] == symbol_name
                assert search_response.json()[0]["file_path"] == file_path

            assert test_client.get(
                f"/api/v1/index/{workspace_id}/symbols",
                params={"q": "generated"},
            ).json() == []
            assert test_client.get(
                f"/api/v1/index/{workspace_id}/symbols",
                params={"q": "dependency"},
            ).json() == []
    finally:
        asyncio.run(dispose_database_engine())
        asyncio.run(
            delete_workspace_index(
                workspace_id
            )
        )
        asyncio.run(dispose_database_engine())
        shutil.rmtree(
            workspace_path,
            ignore_errors=True,
        )
