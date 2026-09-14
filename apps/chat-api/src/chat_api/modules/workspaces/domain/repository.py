"""Workspace Repository interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
import uuid

from chat_api.modules.workspaces.domain.entity import Workspace


class WorkspaceRepository(ABC):
    @abstractmethod
    def get_by_id(self, workspace_id: uuid.UUID) -> Workspace | None:
        pass

    @abstractmethod
    def get_by_slug(self, slug: str) -> Workspace | None:
        pass

    @abstractmethod
    def save(self, workspace: Workspace) -> Workspace:
        pass
