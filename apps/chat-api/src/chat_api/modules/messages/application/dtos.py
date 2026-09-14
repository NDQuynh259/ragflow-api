"""Application DTOs for Messages and Citations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
import uuid


@dataclass(frozen=True)
class CitationDTO:
    id: uuid.UUID
    message_id: uuid.UUID
    chunk_id: str
    document_id: uuid.UUID
    page_number: int
    bbox: list[float] = field(default_factory=list)
    quote: str | None = None
    relevance_score: float | None = None


@dataclass(frozen=True)
class MessageDTO:
    id: uuid.UUID
    session_id: uuid.UUID
    role: str
    content: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float | None = None
    citations: list[CitationDTO] = field(default_factory=list)
    created_at: datetime | None = None
