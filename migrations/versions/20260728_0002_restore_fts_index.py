"""Restore the full-text GIN index.

Revision ID: 20260728_0002
Revises: cfc53009db86
Create Date: 2026-07-28
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260728_0002"
down_revision: Union[str, Sequence[str], None] = "cfc53009db86"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_document_chunks_fts_simple
        ON document_chunks
        USING gin (to_tsvector('simple', content))
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_fts_simple")
