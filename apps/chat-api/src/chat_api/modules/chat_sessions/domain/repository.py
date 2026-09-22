"""ChatSession Repository interface."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

from chat_api.modules.chat_sessions.domain.entity import ChatSession


class ChatSessionRepository(ABC):
    @abstractmethod
    def get_by_id(self, session_id: uuid.UUID) -> ChatSession | None:
        pass

    @abstractmethod
    def list_by_workspace(
        self,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ChatSession]:
        pass

    @abstractmethod
    def save(self, session: ChatSession) -> ChatSession:
        pass

    @abstractmethod
    def delete(self, session_id: uuid.UUID) -> bool:
        pass
