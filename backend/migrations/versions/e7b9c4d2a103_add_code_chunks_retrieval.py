"""add code chunks retrieval

Revision ID: e7b9c4d2a103
Revises: b4f6a8d2c901
Create Date: 2026-07-29

"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector


revision: str = "e7b9c4d2a103"
down_revision: str | None = "b4f6a8d2c901"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


EMBEDDING_DIMENSIONS = 1536


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "code_chunks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            sa.String(length=36),
            nullable=False,
        ),
        sa.Column(
            "file_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "symbol_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "chunk_type",
            sa.String(length=30),
            nullable=False,
        ),
        sa.Column(
            "file_path",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "language",
            sa.String(length=32),
            nullable=False,
        ),
        sa.Column(
            "symbol_name",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "symbol_kind",
            sa.String(length=30),
            nullable=True,
        ),
        sa.Column(
            "start_line",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "end_line",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "chunk_index",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "content",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "content_hash",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "embedding_model",
            sa.String(length=100),
            nullable=True,
        ),
        sa.Column(
            "embedding",
            Vector(EMBEDDING_DIMENSIONS),
            nullable=True,
        ),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(
                """
setweight(to_tsvector('simple', coalesce(file_path, '')), 'A') ||
setweight(to_tsvector('simple', coalesce(symbol_name, '')), 'A') ||
setweight(to_tsvector('simple', coalesce(symbol_kind, '')), 'B') ||
setweight(to_tsvector('simple', coalesce(language, '')), 'B') ||
setweight(to_tsvector('simple', coalesce(content, '')), 'C')
                """,
                persisted=True,
            ),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["repository_files.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["symbol_id"],
            ["code_symbols.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_code_chunks_chunk_type"),
        "code_chunks",
        ["chunk_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_code_chunks_content_hash"),
        "code_chunks",
        ["content_hash"],
        unique=False,
    )
    op.create_index(
        op.f("ix_code_chunks_file_id"),
        "code_chunks",
        ["file_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_code_chunks_symbol_id"),
        "code_chunks",
        ["symbol_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_code_chunks_workspace_id"),
        "code_chunks",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_code_chunks_search_vector",
        "code_chunks",
        ["search_vector"],
        postgresql_using="gin",
    )
    op.execute(
        """
CREATE INDEX ix_code_chunks_embedding_hnsw
ON code_chunks
USING hnsw (embedding vector_cosine_ops)
WHERE embedding IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS ix_code_chunks_embedding_hnsw"
    )
    op.drop_index(
        "ix_code_chunks_search_vector",
        table_name="code_chunks",
    )
    op.drop_index(
        op.f("ix_code_chunks_workspace_id"),
        table_name="code_chunks",
    )
    op.drop_index(
        op.f("ix_code_chunks_symbol_id"),
        table_name="code_chunks",
    )
    op.drop_index(
        op.f("ix_code_chunks_file_id"),
        table_name="code_chunks",
    )
    op.drop_index(
        op.f("ix_code_chunks_content_hash"),
        table_name="code_chunks",
    )
    op.drop_index(
        op.f("ix_code_chunks_chunk_type"),
        table_name="code_chunks",
    )
    op.drop_table("code_chunks")
