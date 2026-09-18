"""ChatSession Domain Aggregate."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from core.domain import AggregateRoot
from core.uuid7 import uuid7


@dataclass(kw_only=True)
class ChatSession(AggregateRoot[uuid.UUID]):
    id: uuid.UUID = field(default_factory=uuid7)
    workspace_id: uuid.UUID
    user_id: uuid.UUID | None = None
    title: str = "New Chat"
    rag_config: dict[str, Any] = field(default_factory=lambda: {"top_k": 5, "rerank": True})
    deleted_at: datetime | None = None
    attached_document_ids: list[uuid.UUID] = field(default_factory=list)

    def update_title(self, new_title: str) -> None:
        self.title = new_title.strip() or "Untitled Chat"
        self.updated_at = datetime.now(UTC)

    def update_rag_config(self, config: dict[str, Any]) -> None:
        self.rag_config.update(config)
        self.updated_at = datetime.now(UTC)

    def attach_document(self, document_id: uuid.UUID) -> None:
        if document_id not in self.attached_document_ids:
            self.attached_document_ids.append(document_id)
            self.updated_at = datetime.now(UTC)

    def detach_document(self, document_id: uuid.UUID) -> None:
        if document_id in self.attached_document_ids:
            self.attached_document_ids.remove(document_id)
            self.updated_at = datetime.now(UTC)
