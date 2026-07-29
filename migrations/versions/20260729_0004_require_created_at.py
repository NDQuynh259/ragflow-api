"""Require creation timestamps for audited entities.

Revision ID: 20260729_0004
Revises: 20260729_0003
Create Date: 2026-07-29
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260729_0004"
down_revision: Union[str, Sequence[str], None] = "20260729_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table_name in ("documents", "document_chunks"):
        op.execute(
            f"UPDATE {table_name} SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"
        )
        op.alter_column(
            table_name,
            "created_at",
            existing_type=sa.DateTime(),
            nullable=False,
        )


def downgrade() -> None:
    for table_name in ("document_chunks", "documents"):
        op.alter_column(
            table_name,
            "created_at",
            existing_type=sa.DateTime(),
            nullable=True,
        )
