"""Generate validated vector embeddings for repository and query text."""

from typing import Any, Protocol

from openai import AsyncOpenAI

from app.core.config import settings
from app.services.hardening.retries import (
    RetryPolicy,
    retry_async,
)


class EmbeddingConfigurationError(RuntimeError):
    """Raised when the embedding provider cannot be configured safely."""


class EmbeddingDimensionError(RuntimeError):
    """Raised when a provider returns a vector with the wrong dimensions."""


class EmbeddingClient(Protocol):
    """Define the provider interface consumed by indexing and retrieval."""

    model: str
    dimensions: int
    batch_size: int

    async def embed(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        """Return one embedding vector for every input string."""
        ...


def validate_embedding_dimensions(
    embedding: list[float],
    expected_dimensions: int,
) -> None:
    """Reject vectors that are incompatible with the pgvector column."""
    if len(embedding) != expected_dimensions:
        raise EmbeddingDimensionError(
            "Embedding dimension mismatch: "
            f"expected {expected_dimensions}, "
            f"got {len(embedding)}"
        )


class OpenAIEmbeddingClient:
    """Batch and retry embedding requests made through the OpenAI client."""

    def __init__(
        self,
        *,
        api_key: str | None = settings.openai_api_key,
        model: str = settings.embedding_model,
        dimensions: int = settings.embedding_dimensions,
        batch_size: int = settings.embedding_batch_size,
        openai_client: Any | None = None,
    ) -> None:
        """Store provider settings and an optional injected test client."""
        self.api_key = api_key
        self.model = model
        self.dimensions = dimensions
        self.batch_size = batch_size
        self._client = openai_client

    def get_client(self):
        """Lazily create and cache the configured asynchronous API client."""
        if self._client is not None:
            return self._client

        if not self.api_key:
            raise EmbeddingConfigurationError(
                "OPENAI_API_KEY is required for embedding generation"
            )

        self._client = AsyncOpenAI(
            api_key=self.api_key,
            timeout=settings.openai_timeout_seconds,
            max_retries=0,
        )

        return self._client

    async def embed(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        """Embed input texts in stable order using bounded provider batches."""
        if not texts:
            return []

        if self.batch_size <= 0:
            raise EmbeddingConfigurationError(
                "embedding batch size must be greater than zero"
            )

        client = self.get_client()
        embeddings: list[list[float]] = []

        for start in range(
            0,
            len(texts),
            self.batch_size,
        ):
            batch = texts[
                start : start + self.batch_size
            ]
            response = await retry_async(
                lambda: client.embeddings.create(
                    model=self.model,
                    input=batch,
                    dimensions=self.dimensions,
                ),
                policy=RetryPolicy(
                    max_attempts=settings.provider_max_retries,
                ),
            )
            response_data = sorted(
                response.data,
                key=lambda item: item.index,
            )

            for item in response_data:
                embedding = list(
                    item.embedding
                )
                validate_embedding_dimensions(
                    embedding,
                    self.dimensions,
                )
                embeddings.append(embedding)

        return embeddings
