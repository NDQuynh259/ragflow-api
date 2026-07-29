"""Add audit columns to documents and document chunks.

Revision ID: 20260729_0003
Revises: 20260728_0002
Create Date: 2026-07-29
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260729_0003"
down_revision: Union[str, Sequence[str], None] = "20260728_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table_name in ("documents", "document_chunks"):
        op.add_column(
            table_name,
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
        )
        op.add_column(table_name, sa.Column("created_by", sa.String(length=255), nullable=True))
        op.add_column(table_name, sa.Column("updated_by", sa.String(length=255), nullable=True))
        op.add_column(table_name, sa.Column("deleted_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    for table_name in ("document_chunks", "documents"):
        op.drop_column(table_name, "deleted_at")
        op.drop_column(table_name, "updated_by")
        op.drop_column(table_name, "created_by")
        op.drop_column(table_name, "updated_at")
