"""Add normalized workspace roles and permissions.

Revision ID: 005_workspace_rbac
Revises: 004_hash_session_tokens
Create Date: 2026-09-16 00:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "005_workspace_rbac"
down_revision: Union[str, None] = "004_hash_session_tokens"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PERMISSIONS = (
    ("workspace:read", "Read workspace"),
    ("workspace:update", "Update workspace"),
    ("workspace:delete", "Delete workspace"),
    ("workspace:manage_members", "Manage workspace members"),
    ("documents:read", "Read documents"),
    ("documents:create", "Create documents"),
    ("documents:delete", "Delete documents"),
    ("sessions:read", "Read chat sessions"),
    ("sessions:create", "Create chat sessions"),
    ("sessions:update", "Update chat sessions"),
    ("sessions:delete", "Delete chat sessions"),
    ("messages:send", "Send messages"),
)

MEMBER_PERMISSIONS = {
    "workspace:read",
    "documents:read",
    "sessions:read",
    "sessions:create",
    "sessions:update",
    "sessions:delete",
    "messages:send",
}


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column("code", sa.String(50), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
    )
    op.create_table(
        "permissions",
        sa.Column("code", sa.String(100), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
    )
    op.create_table(
        "role_permissions",
        sa.Column(
            "role_code",
            sa.String(50),
            sa.ForeignKey("roles.code", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "permission_code",
            sa.String(100),
            sa.ForeignKey("permissions.code", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    roles_table = sa.table(
        "roles",
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
    )
    permissions_table = sa.table(
        "permissions",
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
    )
    role_permissions_table = sa.table(
        "role_permissions",
        sa.column("role_code", sa.String),
        sa.column("permission_code", sa.String),
    )

    op.bulk_insert(
        roles_table,
        [
            {"code": "owner", "name": "Owner", "description": "Full workspace access"},
            {"code": "admin", "name": "Admin", "description": "Workspace administration"},
            {"code": "member", "name": "Member", "description": "Standard workspace access"},
        ],
    )
    op.bulk_insert(
        permissions_table,
        [
            {"code": code, "name": name, "description": None}
            for code, name in PERMISSIONS
        ],
    )
    op.bulk_insert(
        role_permissions_table,
        [
            {"role_code": role, "permission_code": permission}
            for role in ("owner", "admin", "member")
            for permission, _ in PERMISSIONS
            if role == "owner"
            or (role == "admin" and permission != "workspace:delete")
            or (role == "member" and permission in MEMBER_PERMISSIONS)
        ],
    )

    op.drop_constraint(
        op.f("ck_workspace_members_ck_workspace_member_role"),
        "workspace_members",
        type_="check",
    )
    op.create_foreign_key(
        "fk_workspace_members_role_roles",
        "workspace_members",
        "roles",
        ["role"],
        ["code"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.execute(
        "UPDATE workspace_members SET role = 'member' "
        "WHERE role NOT IN ('owner', 'admin', 'member')"
    )
    op.drop_constraint(
        "fk_workspace_members_role_roles",
        "workspace_members",
        type_="foreignkey",
    )
    op.create_check_constraint(
        op.f("ck_workspace_members_ck_workspace_member_role"),
        "workspace_members",
        "role IN ('owner', 'admin', 'member')",
    )
    op.drop_table("role_permissions")
    op.drop_table("permissions")
    op.drop_table("roles")
