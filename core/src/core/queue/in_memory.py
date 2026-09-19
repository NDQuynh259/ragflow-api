"""In-memory queue adapter for testing and offline development."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from core.queue.port import IngestionQueuePort
from core.uuid7 import uuid7_str


class InMemoryQueueAdapter(IngestionQueuePort):
    """In-memory queue adapter storing dispatched jobs in a list."""

    def __init__(self) -> None:
        self.enqueued_jobs: list[dict[str, Any]] = []

    def enqueue(
        self,
        action: str,
        payload: dict[str, Any],
        job_id: str | uuid.UUID | None = None,
        routing_key: str | None = None,
    ) -> str:
        resolved_job_id = str(job_id) if job_id else uuid7_str()
        job_entry: dict[str, Any] = {
            "job_id": resolved_job_id,
            "action": action,
            "routing_key": routing_key,
            "enqueued_at": datetime.now(UTC).isoformat(),
            **payload,
        }
        self.enqueued_jobs.append(job_entry)
        return resolved_job_id

    def enqueue_ingestion(
        self,
        document_id: uuid.UUID,
        job_id: uuid.UUID,
        storage_uri: str,
        workspace_id: uuid.UUID,
    ) -> None:
        self.enqueue(
            action="index",
            payload={
                "document_id": str(document_id),
                "storage_uri": storage_uri,
                "workspace_id": str(workspace_id),
            },
            job_id=job_id,
        )

    def clear(self) -> None:
        """Clear all enqueued jobs."""
        self.enqueued_jobs.clear()


__all__ = ["InMemoryQueueAdapter"]
