"""Add active_workspace_id to user_sessions table.

Revision ID: 003_session_active_workspace
Revises: 002_user_sessions
Create Date: 2026-09-15 17:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "003_session_active_workspace"
down_revision: Union[str, None] = "002_user_sessions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_sessions",
        sa.Column(
            "active_workspace_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_user_sessions_active_workspace_id",
        "user_sessions",
        ["active_workspace_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_sessions_active_workspace_id", table_name="user_sessions")
    op.drop_column("user_sessions", "active_workspace_id")
