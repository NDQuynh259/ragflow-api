"""Workspace Repository interface."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

from chat_api.modules.workspaces.domain.entity import Workspace


class WorkspaceRepository(ABC):
    @abstractmethod
    def get_by_id(self, workspace_id: uuid.UUID) -> Workspace | None:
        pass

    @abstractmethod
    def get_by_slug(self, slug: str) -> Workspace | None:
        pass

    @abstractmethod
    def list_by_user_id(self, user_id: uuid.UUID) -> list[Workspace]:
        pass

    @abstractmethod
    def get_member_role(self, workspace_id: uuid.UUID, user_id: uuid.UUID) -> str | None:
        pass

    @abstractmethod
    def list_permissions(self, workspace_id: uuid.UUID, user_id: uuid.UUID) -> frozenset[str]:
        pass

    @abstractmethod
    def has_permission(
        self,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        permission_code: str,
    ) -> bool:
        pass

    @abstractmethod
    def save(self, workspace: Workspace) -> Workspace:
        pass
