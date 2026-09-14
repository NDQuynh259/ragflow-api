"""Shared Unit of Work interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Self

if TYPE_CHECKING:
    from chat_api.modules.documents.domain.repository import DocumentRepository
    from chat_api.modules.messages.domain.repository import MessageRepository
    from chat_api.modules.sessions.domain.repository import ChatSessionRepository
    from chat_api.modules.users.domain.repository import UserRepository
    from chat_api.modules.workspaces.domain.repository import WorkspaceRepository


class UnitOfWork(ABC):
    """Abstract Unit of Work context manager ensuring atomic transaction boundaries."""

    sessions: ChatSessionRepository
    documents: DocumentRepository
    messages: MessageRepository
    workspaces: WorkspaceRepository
    users: UserRepository

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type is not None:
            self.rollback()
        else:
            self.commit()

    @abstractmethod
    def commit(self) -> None:
        """Commit the current transaction."""
        pass

    @abstractmethod
    def rollback(self) -> None:
        """Rollback the current transaction."""
        pass
