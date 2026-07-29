from typing import Any, Protocol

from openai import AsyncOpenAI

from app.core.config import settings


class EmbeddingConfigurationError(RuntimeError):
    pass


class EmbeddingDimensionError(RuntimeError):
    pass


class EmbeddingClient(Protocol):
    model: str
    dimensions: int
    batch_size: int

    async def embed(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        ...


def validate_embedding_dimensions(
    embedding: list[float],
    expected_dimensions: int,
) -> None:
    if len(embedding) != expected_dimensions:
        raise EmbeddingDimensionError(
            "Embedding dimension mismatch: "
            f"expected {expected_dimensions}, "
            f"got {len(embedding)}"
        )


class OpenAIEmbeddingClient:
    def __init__(
        self,
        *,
        api_key: str | None = settings.openai_api_key,
        model: str = settings.embedding_model,
        dimensions: int = settings.embedding_dimensions,
        batch_size: int = settings.embedding_batch_size,
        openai_client: Any | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.dimensions = dimensions
        self.batch_size = batch_size
        self._client = openai_client

    def get_client(self):
        if self._client is not None:
            return self._client

        if not self.api_key:
            raise EmbeddingConfigurationError(
                "OPENAI_API_KEY is required for embedding generation"
            )

        self._client = AsyncOpenAI(
            api_key=self.api_key
        )

        return self._client

    async def embed(
        self,
        texts: list[str],
    ) -> list[list[float]]:
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
            response = await client.embeddings.create(
                model=self.model,
                input=batch,
                dimensions=self.dimensions,
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
