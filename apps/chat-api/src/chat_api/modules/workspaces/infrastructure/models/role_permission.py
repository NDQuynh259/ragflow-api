"""RolePermission SQLAlchemy ORM association model."""

from __future__ import annotations

from typing import TYPE_CHECKING
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import (
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)

if TYPE_CHECKING:
    from chat_api.modules.workspaces.infrastructure.models.permission import Permission
    from chat_api.modules.workspaces.infrastructure.models.role import Role


class RolePermission(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint(
            "role_code",
            "permission_code",
            name="uq_role_permissions_role_code_permission_code",
        ),
    )

    role_code: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("roles.code", ondelete="CASCADE"),
        nullable=False,
    )
    permission_code: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("permissions.code", ondelete="CASCADE"),
        nullable=False,
    )

    role: Mapped[Role] = relationship("Role", back_populates="permissions")
    permission: Mapped[Permission] = relationship("Permission", back_populates="roles")
