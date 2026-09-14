"""User Domain Entity."""

from __future__ import annotations

from dataclasses import dataclass
import uuid

from chat_api.shared.domain.base_entity import AggregateRoot


@dataclass(kw_only=True)
class User(AggregateRoot[uuid.UUID]):
    email: str
    full_name: str | None = None
    hashed_password: str = ""
    is_active: bool = True
