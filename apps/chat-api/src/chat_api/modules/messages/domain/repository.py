"""Message Repository interface."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

from chat_api.modules.messages.domain.entity import Message


class MessageRepository(ABC):
    @abstractmethod
    def get_by_id(self, message_id: uuid.UUID) -> Message | None:
        pass

    @abstractmethod
    def list_by_session(
        self,
        session_id: uuid.UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Message]:
        pass

    @abstractmethod
    def save(self, message: Message) -> Message:
        pass
