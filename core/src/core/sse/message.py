"""W3C Server-Sent Events (SSE) data structures and encoding."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from core.uuid7 import uuid7_str


@dataclass
class SSEMessage:
    """Represents a Server-Sent Event conforming to the W3C EventSource standard.

    Specification: https://html.spec.whatwg.org/multipage/server-sent-events.html
    """

    event: str | None = None
    data: Any = None
    id: str | None = field(default_factory=uuid7_str)
    retry: int | None = 5000
    comment: str | None = None
    workspace_id: str | None = None
    timestamp: float = field(default_factory=time.time)

    def encode(self) -> str:
        """Encode message into the text/event-stream wire format."""
        if self.comment is not None:
            return f": {self.comment}\n\n"

        lines: list[str] = []

        if self.id is not None:
            lines.append(f"id: {self.id}")

        if self.event is not None:
            lines.append(f"event: {self.event}")

        if self.retry is not None:
            lines.append(f"retry: {self.retry}")

        if self.data is not None:
            if isinstance(self.data, (dict, list)):
                payload_str = json.dumps(self.data, ensure_ascii=False)
            else:
                payload_str = str(self.data)

            for line in payload_str.splitlines():
                lines.append(f"data: {line}")
        else:
            lines.append("data: ")

        lines.append("")
        lines.append("")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Convert message to a dictionary representation."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SSEMessage:
        """Construct an SSEMessage from a dictionary."""
        return cls(
            event=data.get("event"),
            data=data.get("data"),
            id=data.get("id"),
            retry=data.get("retry", 5000),
            comment=data.get("comment"),
            workspace_id=data.get("workspace_id"),
            timestamp=data.get("timestamp", time.time()),
        )


# ==============================================================================
# Domain Event Helpers
# ==============================================================================


def ping_message(comment: str = "ping") -> SSEMessage:
    """Create an SSE keep-alive heartbeat comment message."""
    return SSEMessage(comment=comment, id=None, retry=None)


def document_progress_message(
    workspace_id: str | uuid.UUID,
    document_id: str | uuid.UUID,
    job_id: str | uuid.UUID,
    step: str,
    percent: int,
    details: str | None = None,
) -> SSEMessage:
    """Create a document ingestion progress event message."""
    return SSEMessage(
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


def document_ready_message(
    workspace_id: str | uuid.UUID,
    document_id: str | uuid.UUID,
    job_id: str | uuid.UUID,
    pages: int,
    chunks: int,
) -> SSEMessage:
    """Create a document ingestion completion event message."""
    return SSEMessage(
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


def document_failed_message(
    workspace_id: str | uuid.UUID,
    document_id: str | uuid.UUID,
    job_id: str | uuid.UUID,
    error: str,
) -> SSEMessage:
    """Create a document ingestion failure event message."""
    return SSEMessage(
        event="document_failed",
        workspace_id=str(workspace_id),
        data={
            "job_id": str(job_id),
            "document_id": str(document_id),
            "status": "failed",
            "error": error,
        },
    )


def chat_token_message(
    workspace_id: str | uuid.UUID,
    session_id: str | uuid.UUID,
    message_id: str | uuid.UUID,
    delta: str,
) -> SSEMessage:
    """Create a streaming LLM token chunk event message."""
    return SSEMessage(
        event="chat_token",
        workspace_id=str(workspace_id),
        data={
            "session_id": str(session_id),
            "message_id": str(message_id),
            "delta": delta,
        },
    )


def chat_done_message(
    workspace_id: str | uuid.UUID,
    session_id: str | uuid.UUID,
    message_id: str | uuid.UUID,
    citations: list[dict[str, Any]] | None = None,
) -> SSEMessage:
    """Create a streaming chat completion event message."""
    return SSEMessage(
        event="chat_done",
        workspace_id=str(workspace_id),
        data={
            "session_id": str(session_id),
            "message_id": str(message_id),
            "citations": citations or [],
        },
    )


__all__ = [
    "SSEMessage",
    "ping_message",
    "document_progress_message",
    "document_ready_message",
    "document_failed_message",
    "chat_token_message",
    "chat_done_message",
]
