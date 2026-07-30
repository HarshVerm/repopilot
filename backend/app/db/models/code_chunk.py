"""Persist code chunks for structural, full-text, and vector retrieval."""

import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Index,
    Computed,
    ForeignKey,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import (
    TSVECTOR,
    UUID,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from app.core.config import settings
from app.db.base import Base


SEARCH_VECTOR_EXPRESSION = """
setweight(to_tsvector('simple', coalesce(file_path, '')), 'A') ||
setweight(to_tsvector('simple', coalesce(symbol_name, '')), 'A') ||
setweight(to_tsvector('simple', coalesce(symbol_kind, '')), 'B') ||
setweight(to_tsvector('simple', coalesce(language, '')), 'B') ||
setweight(to_tsvector('simple', coalesce(content, '')), 'C')
"""


class CodeChunk(Base):
    """Store one searchable source window and its retrieval metadata."""

    __tablename__ = "code_chunks"
    __table_args__ = (
        Index(
            "ix_code_chunks_search_vector",
            "search_vector",
            postgresql_using="gin",
        ),
        Index(
            "ix_code_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={
                "embedding": "vector_cosine_ops",
            },
            postgresql_where=text(
                "embedding IS NOT NULL"
            ),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        index=True,
    )

    file_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "repository_files.id",
            ondelete="CASCADE",
        ),
        index=True,
    )

    symbol_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "code_symbols.id",
            ondelete="SET NULL",
        ),
        index=True,
        nullable=True,
    )

    chunk_type: Mapped[str] = mapped_column(
        String(30),
        index=True,
    )

    file_path: Mapped[str] = mapped_column(
        Text
    )

    language: Mapped[str] = mapped_column(
        String(32)
    )

    symbol_name: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    symbol_kind: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    start_line: Mapped[int] = mapped_column(
        Integer
    )

    end_line: Mapped[int] = mapped_column(
        Integer
    )

    chunk_index: Mapped[int] = mapped_column(
        Integer
    )

    content: Mapped[str] = mapped_column(
        Text
    )

    content_hash: Mapped[str] = mapped_column(
        String(64),
        index=True,
    )

    embedding_model: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(settings.embedding_dimensions),
        nullable=True,
    )

    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed(
            SEARCH_VECTOR_EXPRESSION,
            persisted=True,
        ),
        nullable=True,
    )

    file = relationship(
        "RepositoryFile",
        back_populates="chunks",
    )

    symbol = relationship(
        "CodeSymbol",
        back_populates="chunks",
    )
