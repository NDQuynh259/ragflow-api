"""Add image URL to message citations.

Revision ID: 007_message_citation_image_url
Revises: 006_rbac_ids_and_timestamps
Create Date: 2026-10-10 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "007_message_citation_image_url"
down_revision: str | None = "006_rbac_ids_and_timestamps"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("message_citations", sa.Column("image_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("message_citations", "image_url")
