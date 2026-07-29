import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Computed,
    ForeignKey,
    Integer,
    String,
    Text,
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
    __tablename__ = "code_chunks"

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
