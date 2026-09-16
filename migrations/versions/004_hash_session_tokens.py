"""Hash legacy plaintext session tokens.

Revision ID: 004_hash_session_tokens
Revises: 003_session_active_workspace
Create Date: 2026-09-16 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

revision: str = "004_hash_session_tokens"
down_revision: Union[str, None] = "003_session_active_workspace"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE user_sessions "
        "SET token = encode(digest(token, 'sha256'), 'hex')"
    )


def downgrade() -> None:
    # Hashes cannot be converted back to credentials accepted by older code.
    op.execute("DELETE FROM user_sessions")
