"""Presentation DTOs for Chat Sessions."""

from __future__ import annotations

from datetime import datetime
from typing import Any
import uuid
from pydantic import BaseModel, Field

from chat_api.shared.presentation import ApiResponse, PaginatedResponse


class CreateSessionRequest(BaseModel):
    workspace_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    title: str = Field(default="New Chat", max_length=255)
    rag_config: dict[str, Any] = Field(
        default_factory=lambda: {"top_k": 5, "rerank": True}
    )


class AttachDocumentRequest(BaseModel):
    document_id: uuid.UUID


class SessionResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID | None
    title: str
    rag_config: dict[str, Any]
    attached_document_ids: list[uuid.UUID] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


# Standardized API response DTO wrappers for chat sessions
SessionApiResponse = ApiResponse[SessionResponse]
SessionListApiResponse = ApiResponse[list[SessionResponse]]
PaginatedSessionResponse = PaginatedResponse[SessionResponse]
