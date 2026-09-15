"""User Domain Entity."""

from __future__ import annotations

from dataclasses import dataclass, field
import uuid

from chat_api.shared.domain.base_entity import AggregateRoot
from chat_api.shared.domain.uuid7 import uuid7


@dataclass(kw_only=True)
class User(AggregateRoot[uuid.UUID]):
    id: uuid.UUID = field(default_factory=uuid7)
    email: str
    full_name: str | None = None
    hashed_password: str = ""
    is_active: bool = True

