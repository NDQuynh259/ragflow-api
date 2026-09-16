"""Shared Unit of Work interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Generator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Self

if TYPE_CHECKING:
    from chat_api.modules.auth.domain.repository import UserSessionRepository
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
    user_sessions: UserSessionRepository

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        try:
            if exc_type is not None:
                self.rollback()
                self.discard_new_events()
            else:
                try:
                    self.commit()
                except Exception:
                    self.rollback()
                    self.discard_new_events()
                    raise
        finally:
            self.close()

    @contextmanager
    def read_only(self) -> Generator[Self, None, None]:
        """Open repositories for a query and never commit its transaction."""
        self.__enter__()
        try:
            yield self
        finally:
            try:
                self.rollback()
            finally:
                self.close()

    def track(self, *aggregates: Any) -> None:
        """Track aggregates whose domain events should be published after commit."""
        tracked = getattr(self, "_tracked_aggregates", None)
        if tracked is None:
            tracked = []
            self._tracked_aggregates = tracked
        for aggregate in aggregates:
            if not any(candidate is aggregate for candidate in tracked):
                tracked.append(aggregate)

    def collect_new_events(self) -> list[Any]:
        events: list[Any] = []
        tracked = getattr(self, "_tracked_aggregates", [])
        for aggregate in tracked:
            poll_events = getattr(aggregate, "poll_events", None)
            if poll_events is not None:
                events.extend(poll_events())
        tracked.clear()
        return events

    def discard_new_events(self) -> None:
        """Drop events produced by a transaction that did not commit."""
        tracked = getattr(self, "_tracked_aggregates", [])
        for aggregate in tracked:
            poll_events = getattr(aggregate, "poll_events", None)
            if poll_events is not None:
                poll_events()
        tracked.clear()

    def close(self) -> None:
        """Release resources owned by this Unit of Work."""

    @abstractmethod
    def commit(self) -> None:
        """Commit the current transaction."""
        pass

    @abstractmethod
    def rollback(self) -> None:
        """Rollback the current transaction."""
        pass
