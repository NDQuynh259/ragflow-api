"""Add id, created_at, updated_at to roles, permissions, and role_permissions.

Revision ID: 006_rbac_ids_and_timestamps
Revises: 005_workspace_rbac
Create Date: 2026-09-16 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "006_rbac_ids_and_timestamps"
down_revision: Union[str, None] = "005_workspace_rbac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Drop foreign keys referencing roles.code and permissions.code
    op.drop_constraint(
        "fk_workspace_members_role_roles",
        "workspace_members",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_role_permissions_role_code_roles",
        "role_permissions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_role_permissions_permission_code_permissions",
        "role_permissions",
        type_="foreignkey",
    )

    # 2. Update roles: add unique on code, add id, created_at, updated_at, swap PK to id
    op.create_unique_constraint("uq_roles_code", "roles", ["code"])
    op.add_column(
        "roles",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v7()"),
            nullable=False,
        ),
    )
    op.add_column(
        "roles",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.add_column(
        "roles",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.drop_constraint("pk_roles", "roles", type_="primary")
    op.create_primary_key("pk_roles", "roles", ["id"])

    # 3. Update permissions: add unique on code, add id, created_at, updated_at, swap PK to id
    op.create_unique_constraint("uq_permissions_code", "permissions", ["code"])
    op.add_column(
        "permissions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v7()"),
            nullable=False,
        ),
    )
    op.add_column(
        "permissions",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.add_column(
        "permissions",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.drop_constraint("pk_permissions", "permissions", type_="primary")
    op.create_primary_key("pk_permissions", "permissions", ["id"])

    # 4. Update role_permissions: add id, created_at, updated_at, swap PK to id, add unique on (role_code, permission_code)
    op.add_column(
        "role_permissions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v7()"),
            nullable=False,
        ),
    )
    op.add_column(
        "role_permissions",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.add_column(
        "role_permissions",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.drop_constraint("pk_role_permissions", "role_permissions", type_="primary")
    op.create_primary_key("pk_role_permissions", "role_permissions", ["id"])
    op.create_unique_constraint(
        "uq_role_permissions_role_code_permission_code",
        "role_permissions",
        ["role_code", "permission_code"],
    )

    # 5. Re-create foreign keys referencing roles.code and permissions.code
    op.create_foreign_key(
        "fk_workspace_members_role_roles",
        "workspace_members",
        "roles",
        ["role"],
        ["code"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_role_permissions_role_code_roles",
        "role_permissions",
        "roles",
        ["role_code"],
        ["code"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_role_permissions_permission_code_permissions",
        "role_permissions",
        "permissions",
        ["permission_code"],
        ["code"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    # 1. Drop foreign keys referencing roles.code and permissions.code
    op.drop_constraint(
        "fk_workspace_members_role_roles",
        "workspace_members",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_role_permissions_role_code_roles",
        "role_permissions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_role_permissions_permission_code_permissions",
        "role_permissions",
        type_="foreignkey",
    )

    # 2. Revert role_permissions
    op.drop_constraint(
        "uq_role_permissions_role_code_permission_code",
        "role_permissions",
        type_="unique",
    )
    op.drop_constraint("pk_role_permissions", "role_permissions", type_="primary")
    op.create_primary_key(
        "pk_role_permissions",
        "role_permissions",
        ["role_code", "permission_code"],
    )
    op.drop_column("role_permissions", "updated_at")
    op.drop_column("role_permissions", "created_at")
    op.drop_column("role_permissions", "id")

    # 3. Revert permissions
    op.drop_constraint("pk_permissions", "permissions", type_="primary")
    op.create_primary_key("pk_permissions", "permissions", ["code"])
    op.drop_constraint("uq_permissions_code", "permissions", type_="unique")
    op.drop_column("permissions", "updated_at")
    op.drop_column("permissions", "created_at")
    op.drop_column("permissions", "id")

    # 4. Revert roles
    op.drop_constraint("pk_roles", "roles", type_="primary")
    op.create_primary_key("pk_roles", "roles", ["code"])
    op.drop_constraint("uq_roles_code", "roles", type_="unique")
    op.drop_column("roles", "updated_at")
    op.drop_column("roles", "created_at")
    op.drop_column("roles", "id")

    # 5. Re-add foreign keys referencing roles.code and permissions.code
    op.create_foreign_key(
        "fk_workspace_members_role_roles",
        "workspace_members",
        "roles",
        ["role"],
        ["code"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_role_permissions_role_code_roles",
        "role_permissions",
        "roles",
        ["role_code"],
        ["code"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_role_permissions_permission_code_permissions",
        "role_permissions",
        "permissions",
        ["permission_code"],
        ["code"],
        ondelete="CASCADE",
    )
