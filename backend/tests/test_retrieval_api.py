import asyncio
import shutil
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
from app.api.routes.retrieval import (
    get_embedding_client,
)
from app.core.config import settings
from app.db.models.code_index import RepositoryFile
from app.db.session import get_db
from app.main import app
from tests.fakes import FakeEmbeddingClient
from tests.retrieval_fixtures import (
    create_retrieval_fixture_repo,
)


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


def override_embedding_client():
    return FakeEmbeddingClient()


@pytest.fixture(autouse=True)
def use_test_dependencies():
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[
        get_embedding_client
    ] = override_embedding_client

    yield

    app.dependency_overrides.pop(
        get_db,
        None,
    )
    app.dependency_overrides.pop(
        get_embedding_client,
        None,
    )


async def delete_workspace(
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


def test_retrieval_build_and_search_api_end_to_end():
    workspace_id = str(uuid.uuid4())
    workspace_path = (
        WORKSPACES_DIR / workspace_id
    )
    repo = workspace_path / "repository"
    create_retrieval_fixture_repo(repo)

    try:
        with TestClient(app) as test_client:
            index_response = test_client.post(
                f"/api/v1/index/{workspace_id}"
            )
            build_response = test_client.post(
                f"/api/v1/retrieval/{workspace_id}/build"
            )
            search_response = test_client.post(
                f"/api/v1/retrieval/{workspace_id}/search",
                json={
                    "query": (
                        "Search request fires for every keypress. "
                        "Wait briefly before calling the API."
                    ),
                    "top_k": 10,
                    "debug": True,
                },
            )

        assert index_response.status_code == 200
        assert build_response.status_code == 200
        assert build_response.json()["chunks_created"] > 0
        assert (
            build_response.json()["chunks_embedded"]
            == build_response.json()["chunks_created"]
        )
        assert search_response.status_code == 200

        body = search_response.json()
        result_paths = {
            result["file_path"]
            for result in body["results"]
        }

        assert {
            "src/hooks/useDebounce.ts",
            "src/utils/debounce.ts",
            "src/components/SearchBox.tsx",
        }.issubset(result_paths)
        assert body["context"]["estimated_tokens"] <= settings.max_context_tokens
        assert body["debug"]["semantic_available"] is True
    finally:
        asyncio.run(dispose_database_engine())
        asyncio.run(
            delete_workspace(
                workspace_id
            )
        )
        asyncio.run(dispose_database_engine())
        shutil.rmtree(
            workspace_path,
            ignore_errors=True,
        )


def test_retrieval_search_api_validation():
    workspace_id = str(uuid.uuid4())

    with TestClient(app) as test_client:
        blank_query = test_client.post(
            f"/api/v1/retrieval/{workspace_id}/search",
            json={
                "query": "   ",
                "top_k": 10,
            },
        )
        invalid_limit = test_client.post(
            f"/api/v1/retrieval/{workspace_id}/search",
            json={
                "query": "debounce",
                "top_k": 99,
            },
        )
        invalid_workspace = test_client.post(
            "/api/v1/retrieval/not-a-uuid/search",
            json={
                "query": "debounce",
                "top_k": 10,
            },
        )

    assert blank_query.status_code == 422
    assert invalid_limit.status_code == 422
    assert invalid_workspace.status_code == 422
