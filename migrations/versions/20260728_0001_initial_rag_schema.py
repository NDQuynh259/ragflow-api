"""Create the multimodal RAG schema.

Revision ID: 20260728_0001
Revises:
Create Date: 2026-07-28
"""

from typing import Sequence, Union

from alembic import op
from pgvector.sqlalchemy import Vector
import sqlalchemy as sa


revision: str = "20260728_0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "documents",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("file_type", sa.String(), nullable=False),
        sa.Column("file_size", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("chunk_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "document_nodes",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("document_id", sa.String(), nullable=False),
        sa.Column("parent_id", sa.String(), nullable=True),
        sa.Column("node_type", sa.String(length=20), nullable=False),
        sa.Column("node_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("structured_data", sa.JSON(), nullable=True),
        sa.Column("object_key", sa.String(), nullable=True),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column(
            "metadata_json",
            sa.JSON(),
            server_default=sa.text("'{}'::json"),
            nullable=False,
        ),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column("vision_embedding", Vector(768), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["document_nodes.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_document_nodes_document_id",
        "document_nodes",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        "ix_document_nodes_document_id_node_index",
        "document_nodes",
        ["document_id", "node_index"],
        unique=False,
    )
    op.execute("""
        CREATE INDEX ix_document_nodes_embedding_hnsw
        ON document_nodes
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)
    op.execute("""
        CREATE INDEX ix_document_nodes_fts_simple
        ON document_nodes
        USING gin (to_tsvector('simple', content))
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_nodes_fts_simple")
    op.execute("DROP INDEX IF EXISTS ix_document_nodes_embedding_hnsw")
    op.drop_index(
        "ix_document_nodes_document_id_node_index",
        table_name="document_nodes",
    )
    op.drop_index(
        "ix_document_nodes_document_id",
        table_name="document_nodes",
    )
    op.drop_table("document_nodes")
    op.drop_table("documents")
