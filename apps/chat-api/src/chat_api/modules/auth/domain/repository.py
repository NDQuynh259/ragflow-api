"""UserSession Repository interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
import uuid

from chat_api.modules.auth.domain.entity import UserSession


class UserSessionRepository(ABC):
    @abstractmethod
    def get_by_token(self, token: str) -> UserSession | None:
        """Fetch an active session using the presented raw token."""
        pass

    @abstractmethod
    def save(self, session: UserSession) -> UserSession:
        """Persist or update user session."""
        pass

    @abstractmethod
    def delete_by_token(self, token: str) -> bool:
        """Invalidate/delete session by token."""
        pass

    @abstractmethod
    def delete_by_user_id(self, user_id: uuid.UUID) -> int:
        """Delete all active sessions for a user (logout all devices)."""
        pass
