"""Schemas and data models for Realtime and Server-Sent Events (SSE)."""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from core.events.formatter import format_sse
from core.uuid7 import uuid7_str


@dataclass(frozen=True)
class RealtimeEvent:
    """Base event model for real-time streaming and event distribution."""

    event: str
    data: dict[str, Any] | str
    id: str = field(default_factory=uuid7_str)
    workspace_id: str | None = None
    retry: int | None = 5000
    timestamp: float = field(default_factory=time.time)

    def to_sse(self) -> str:
        """Serialize event into W3C SSE text block."""
        return format_sse(
            event=self.event,
            data=self.data,
            event_id=self.id,
            retry=self.retry,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert event to dictionary for message broker serialization."""
        return asdict(self)


# ==============================================================================
# Specialized Domain Event Factories
# ==============================================================================


def create_document_progress_event(
    workspace_id: str | uuid.UUID,
    document_id: str | uuid.UUID,
    job_id: str | uuid.UUID,
    step: str,
    percent: int,
    details: str | None = None,
) -> RealtimeEvent:
    """Create a document ingestion progress event."""
    return RealtimeEvent(
        event="document_progress",
        workspace_id=str(workspace_id),
        data={
            "job_id": str(job_id),
            "document_id": str(document_id),
            "step": step,
            "percent": percent,
            "details": details or "",
        },
    )


def create_document_ready_event(
    workspace_id: str | uuid.UUID,
    document_id: str | uuid.UUID,
    job_id: str | uuid.UUID,
    pages: int,
    chunks: int,
) -> RealtimeEvent:
    """Create a document ingestion completed event."""
    return RealtimeEvent(
        event="document_ready",
        workspace_id=str(workspace_id),
        data={
            "job_id": str(job_id),
            "document_id": str(document_id),
            "status": "ready",
            "pages": pages,
            "chunks": chunks,
            "percent": 100,
        },
    )


def create_document_failed_event(
    workspace_id: str | uuid.UUID,
    document_id: str | uuid.UUID,
    job_id: str | uuid.UUID,
    error: str,
) -> RealtimeEvent:
    """Create a document ingestion failure event."""
    return RealtimeEvent(
        event="document_failed",
        workspace_id=str(workspace_id),
        data={
            "job_id": str(job_id),
            "document_id": str(document_id),
            "status": "failed",
            "error": error,
        },
    )


def create_chat_token_event(
    workspace_id: str | uuid.UUID,
    session_id: str | uuid.UUID,
    message_id: str | uuid.UUID,
    delta: str,
) -> RealtimeEvent:
    """Create a streaming chat token chunk event."""
    return RealtimeEvent(
        event="chat_token",
        workspace_id=str(workspace_id),
        data={
            "session_id": str(session_id),
            "message_id": str(message_id),
            "delta": delta,
        },
    )


def create_chat_done_event(
    workspace_id: str | uuid.UUID,
    session_id: str | uuid.UUID,
    message_id: str | uuid.UUID,
    citations: list[dict[str, Any]] | None = None,
) -> RealtimeEvent:
    """Create a chat stream completed event."""
    return RealtimeEvent(
        event="chat_done",
        workspace_id=str(workspace_id),
        data={
            "session_id": str(session_id),
            "message_id": str(message_id),
            "citations": citations or [],
        },
    )


__all__ = [
    "RealtimeEvent",
    "create_document_progress_event",
    "create_document_ready_event",
    "create_document_failed_event",
    "create_chat_token_event",
    "create_chat_done_event",
]
