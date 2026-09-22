"""User Repository interface."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

from chat_api.modules.users.domain.entity import User


class UserRepository(ABC):
    @abstractmethod
    def get_by_id(self, user_id: uuid.UUID) -> User | None:
        pass

    @abstractmethod
    def get_by_email(self, email: str) -> User | None:
        pass

    @abstractmethod
    def save(self, user: User) -> User:
        pass
