"""In-memory queue adapter for testing and offline development."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from core.queue.constants import Actions
from core.queue.port import IngestionQueuePort
from core.queue.schema import DocumentJobPayload, JobEnvelope
from core.uuid7 import uuid7_str


class InMemoryQueueAdapter(IngestionQueuePort):
    """In-memory queue adapter storing dispatched JobEnvelope items in a list.

    Provides inspection methods for unit testing without requiring an external broker.
    """

    def __init__(self) -> None:
        self.enqueued_jobs: list[JobEnvelope] = []

    def enqueue(
        self,
        action: str,
        payload: dict[str, Any],
        job_id: str | uuid.UUID | None = None,
        routing_key: str | None = None,
        correlation_id: str | None = None,
    ) -> str:
        resolved_job_id = str(job_id) if job_id else uuid7_str()
        envelope = JobEnvelope(
            job_id=resolved_job_id,
            action=action,
            payload=payload,
            routing_key=routing_key,
            correlation_id=correlation_id,
            enqueued_at=datetime.now(UTC).isoformat(),
        )
        self.enqueued_jobs.append(envelope)
        return resolved_job_id

    def enqueue_ingestion(
        self,
        document_id: uuid.UUID,
        job_id: uuid.UUID,
        storage_uri: str,
        workspace_id: uuid.UUID,
    ) -> None:
        payload = DocumentJobPayload.create(
            document_id=document_id,
            storage_uri=storage_uri,
            workspace_id=workspace_id,
        ).to_dict()

        self.enqueue(
            action=Actions.INDEX,
            payload=payload,
            job_id=job_id,
        )

    def get_jobs_for_action(self, action: str) -> list[JobEnvelope]:
        """Filter enqueued jobs by action type."""
        return [job for job in self.enqueued_jobs if job.action == action]

    def clear(self) -> None:
        """Clear all enqueued jobs."""
        self.enqueued_jobs.clear()

    def check_health(self) -> bool:
        return True

    def close(self) -> None:
        self.clear()


__all__ = ["InMemoryQueueAdapter"]
