import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.api.routes.publishing import (
    get_publication_service,
)
from app.core.config import settings
from app.db.session import (
    engine,
    get_db,
)
from app.main import app
from app.services.publishing.service import (
    PublicationService,
)
from tests.publishing_fixtures import (
    FakeGitHubPublisher,
    StaticAuthenticator,
    cleanup_publishing_workspace,
    prepare_publishing_workspace,
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


async def dispose_database_engine() -> None:
    await engine.dispose()


async def dispose_test_database_engine() -> None:
    await test_engine.dispose()


@pytest.fixture(autouse=True)
def clear_publication_overrides():
    yield

    app.dependency_overrides.pop(
        get_db,
        None,
    )
    app.dependency_overrides.pop(
        get_publication_service,
        None,
    )


def test_publish_and_lookup_publication_api():
    workspace = prepare_publishing_workspace()
    github = FakeGitHubPublisher()
    service = PublicationService(
        github_publisher=github,
        authenticator=StaticAuthenticator(),
    )
    app.dependency_overrides[
        get_db
    ] = override_get_db
    app.dependency_overrides[
        get_publication_service
    ] = lambda: service
    asyncio.run(
        dispose_database_engine()
    )

    try:
        with TestClient(app) as test_client:
            publish_response = test_client.post(
                f"/api/v1/reviews/{workspace.review.id}/publish"
            )

            assert publish_response.status_code == 200
            body = publish_response.json()
            assert body["status"] == "published"
            assert body["repository"] == {
                "owner": "acme",
                "name": "storefront",
            }
            assert body["head_branch"].startswith(
                "repopilot/142-"
            )
            assert body["pull_request_number"] == 1

            get_response = test_client.get(
                f"/api/v1/publications/{body['publication_id']}"
            )
            by_review_response = test_client.get(
                f"/api/v1/reviews/{workspace.review.id}/publication"
            )

        assert get_response.status_code == 200
        assert by_review_response.status_code == 200
        assert get_response.json()["publication_id"] == body["publication_id"]
        assert by_review_response.json()["publication_id"] == body["publication_id"]
        assert len(github.created_requests) == 1
    finally:
        asyncio.run(
            cleanup_publishing_workspace(
                workspace
            )
        )
        asyncio.run(
            dispose_test_database_engine()
        )
