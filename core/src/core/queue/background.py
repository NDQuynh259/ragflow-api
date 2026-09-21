"""Background job queue adapter for local execution and mock ingestion."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from core.queue.constants import Actions
from core.queue.port import IngestionQueuePort
from core.queue.schema import DocumentJobPayload
from core.uuid7 import uuid7_str

logger = logging.getLogger(__name__)


class BackgroundQueueAdapter(IngestionQueuePort):
    """Local adapter logging and accepting background jobs."""

    def enqueue(
        self,
        action: str,
        payload: dict[str, Any],
        job_id: str | uuid.UUID | None = None,
        routing_key: str | None = None,
        correlation_id: str | None = None,
    ) -> str:
        resolved_job_id = str(job_id) if job_id else uuid7_str()
        logger.info(
            "Enqueued background job %s (action: %s, routing_key: %s, correlation_id: %s)",
            resolved_job_id,
            action,
            routing_key,
            correlation_id,
        )
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

    def check_health(self) -> bool:
        return True

    def close(self) -> None:
        pass


__all__ = ["BackgroundQueueAdapter"]
