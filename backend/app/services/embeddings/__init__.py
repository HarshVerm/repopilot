# Module purpose: Expose the embeddings package.

from app.services.embeddings.client import (
    EmbeddingConfigurationError,
    EmbeddingDimensionError,
    OpenAIEmbeddingClient,
    validate_embedding_dimensions,
)

__all__ = [
    "EmbeddingConfigurationError",
    "EmbeddingDimensionError",
    "OpenAIEmbeddingClient",
    "validate_embedding_dimensions",
]
