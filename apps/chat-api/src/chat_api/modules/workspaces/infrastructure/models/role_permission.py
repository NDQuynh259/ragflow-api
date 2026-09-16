"""RolePermission SQLAlchemy ORM association model."""

from __future__ import annotations

from typing import TYPE_CHECKING
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from chat_api.shared.infrastructure.database.base import Base

if TYPE_CHECKING:
    from chat_api.modules.workspaces.infrastructure.models.permission import Permission
    from chat_api.modules.workspaces.infrastructure.models.role import Role


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_code: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("roles.code", ondelete="CASCADE"),
        primary_key=True,
    )
    permission_code: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("permissions.code", ondelete="CASCADE"),
        primary_key=True,
    )

    role: Mapped[Role] = relationship("Role", back_populates="permissions")
    permission: Mapped[Permission] = relationship("Permission", back_populates="roles")
