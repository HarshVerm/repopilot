# Module purpose: Define persistent code index database models.

import uuid

from sqlalchemy import (
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from sqlalchemy.dialects.postgresql import UUID

from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from app.db.base import Base


# Purpose: Persist repository file records.
class RepositoryFile(Base):
    __tablename__ = "repository_files"

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "file_path",
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

    file_path: Mapped[str] = mapped_column(
        Text
    )

    language: Mapped[str] = mapped_column(
        String(32)
    )

    size_bytes: Mapped[int] = mapped_column(
        Integer
    )

    sha256: Mapped[str] = mapped_column(
        String(64)
    )

    symbols = relationship(
        "CodeSymbol",
        back_populates="file",
        cascade="all, delete-orphan",
    )

    chunks = relationship(
        "CodeChunk",
        back_populates="file",
        cascade="all, delete-orphan",
    )


# Purpose: Persist code symbol records.
class CodeSymbol(Base):
    __tablename__ = "code_symbols"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    file_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "repository_files.id",
            ondelete="CASCADE",
        ),
        index=True,
    )

    kind: Mapped[str] = mapped_column(
        String(30)
    )

    name: Mapped[str] = mapped_column(
        Text,
        index=True,
    )

    start_line: Mapped[int] = mapped_column(
        Integer
    )

    end_line: Mapped[int] = mapped_column(
        Integer
    )

    file = relationship(
        "RepositoryFile",
        back_populates="symbols",
    )

    chunks = relationship(
        "CodeChunk",
        back_populates="symbol",
    )
