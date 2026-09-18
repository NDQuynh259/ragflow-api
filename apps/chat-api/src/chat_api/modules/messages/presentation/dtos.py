"""Presentation DTOs for Messages and Citations."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class SendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, description="Nội dung câu hỏi của người dùng.")


class CitationResponse(BaseModel):
    id: uuid.UUID
    message_id: uuid.UUID
    chunk_id: str
    document_id: uuid.UUID
    page_number: int
    bbox: list[float] = Field(default_factory=list)
    quote: str | None = None
    relevance_score: float | None = None


class MessageResponse(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    role: str
    content: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float | None = None
    citations: list[CitationResponse] = Field(default_factory=list)
    created_at: datetime | None = None
