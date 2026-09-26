"""Workspace application services."""

from __future__ import annotations

from typing import TYPE_CHECKING

from chat_api.modules.workspaces.domain.entity import (
    Workspace,
    WorkspaceMember,
    WorkspaceRole,
)

if TYPE_CHECKING:
    from chat_api.modules.users.domain.entity import User
    from chat_api.shared.infrastructure.database import UnitOfWork


class WorkspaceProvisioningService:
    """Application service for provisioning workspaces and initial memberships."""

    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    def create_default_workspace(self, user: User) -> Workspace:
        """Create and persist a default workspace with OWNER role for a given user."""
        clean_name = user.full_name or user.email.split("@")[0]
        ws_slug = f"workspace-{user.id.hex[-8:]}"
        workspace = Workspace(
            name=f"{clean_name}'s Workspace",
            slug=ws_slug,
            members=[],
        )
        workspace.members.append(
            WorkspaceMember(
                workspace_id=workspace.id,
                user_id=user.id,
                role=WorkspaceRole.OWNER,
            )
        )
        self.uow.workspaces.save(workspace)
        return workspace


__all__ = ["WorkspaceProvisioningService"]
