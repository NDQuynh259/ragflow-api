"""Application DTOs for Chat Sessions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
import uuid


@dataclass(frozen=True)
class SessionDTO:
    id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID | None
    title: str
    rag_config: dict[str, Any]
    attached_document_ids: list[uuid.UUID] = field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None
