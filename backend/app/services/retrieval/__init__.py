# Module purpose: Expose the retrieval package.

from app.services.retrieval.service import (
    build_retrieval_index,
    hybrid_search,
)

__all__ = [
    "build_retrieval_index",
    "hybrid_search",
]
