import asyncio

import pytest

from app.services.embeddings.client import (
    EmbeddingConfigurationError,
    EmbeddingDimensionError,
    OpenAIEmbeddingClient,
    validate_embedding_dimensions,
)
from tests.fakes import FakeOpenAIClient


def test_openai_embedding_client_batches_and_preserves_order():
    fake_openai = FakeOpenAIClient(
        dimensions=3
    )
    embedding_client = OpenAIEmbeddingClient(
        api_key="test-key",
        model="text-embedding-3-small",
        dimensions=3,
        batch_size=2,
        openai_client=fake_openai,
    )

    async def run_test():
        return await embedding_client.embed(
            [
                "first",
                "second",
                "third",
            ]
        )

    embeddings = asyncio.run(run_test())

    assert fake_openai.embeddings.calls == [
        [
            "first",
            "second",
        ],
        [
            "third",
        ],
    ]
    assert embeddings == [
        [
            1.0,
            1.0,
            1.0,
        ],
        [
            2.0,
            2.0,
            2.0,
        ],
        [
            1.0,
            1.0,
            1.0,
        ],
    ]


def test_openai_embedding_client_requires_api_key_when_no_client():
    embedding_client = OpenAIEmbeddingClient(
        api_key=None,
        dimensions=3,
    )

    async def run_test():
        await embedding_client.embed(
            ["query"]
        )

    with pytest.raises(
        EmbeddingConfigurationError
    ):
        asyncio.run(run_test())


def test_validate_embedding_dimensions_rejects_wrong_size():
    with pytest.raises(
        EmbeddingDimensionError,
        match="expected 3, got 2",
    ):
        validate_embedding_dimensions(
            [
                0.1,
                0.2,
            ],
            3,
        )
