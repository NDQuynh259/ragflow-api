"""UserSession Domain Entity."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import uuid

from core.domain import AggregateRoot
from core.uuid7 import uuid7


@dataclass(kw_only=True)
class UserSession(AggregateRoot[uuid.UUID]):
    """Domain entity representing an active user login session."""
    id: uuid.UUID = field(default_factory=uuid7)
    user_id: uuid.UUID
    active_workspace_id: uuid.UUID | None = None
    token: str
    expires_at: datetime
    ip_address: str | None = None
    user_agent: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_expired(self) -> bool:
        now = datetime.now(timezone.utc)
        if self.expires_at.tzinfo is None:
            return self.expires_at.replace(tzinfo=timezone.utc) < now
        return self.expires_at < now
