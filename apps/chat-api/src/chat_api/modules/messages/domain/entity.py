"""Message Domain Aggregate and Entities."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import uuid

from chat_api.shared.domain.base_entity import AggregateRoot, Entity
from chat_api.shared.domain.uuid7 import uuid7


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass(kw_only=True)
class MessageCitation(Entity[uuid.UUID]):
    id: uuid.UUID = field(default_factory=uuid7)
    message_id: uuid.UUID
    chunk_id: str
    document_id: uuid.UUID
    page_number: int
    bbox: list[float] = field(default_factory=list)
    quote: str | None = None
    relevance_score: float | None = None


@dataclass(kw_only=True)
class MessageFeedback(Entity[uuid.UUID]):
    id: uuid.UUID = field(default_factory=uuid7)
    message_id: uuid.UUID
    rating: int  # -1 or 1
    user_id: uuid.UUID | None = None
    comment: str | None = None


@dataclass(kw_only=True)
class Message(AggregateRoot[uuid.UUID]):
    id: uuid.UUID = field(default_factory=uuid7)
    session_id: uuid.UUID
    role: MessageRole
    content: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float | None = None
    citations: list[MessageCitation] = field(default_factory=list)
    feedbacks: list[MessageFeedback] = field(default_factory=list)

    def add_citation(
        self,
        chunk_id: str,
        document_id: uuid.UUID,
        page_number: int,
        bbox: list[float] | None = None,
        quote: str | None = None,
        relevance_score: float | None = None,
    ) -> MessageCitation:
        citation = MessageCitation(
            id=uuid7(),
            message_id=self.id,
            chunk_id=chunk_id,
            document_id=document_id,
            page_number=page_number,
            bbox=bbox or [],
            quote=quote,
            relevance_score=relevance_score,
        )
        self.citations.append(citation)
        return citation
