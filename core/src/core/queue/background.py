"""Background job queue adapter for document ingestion."""

from __future__ import annotations

import logging
import uuid

from core.queue.port import IngestionQueuePort

logger = logging.getLogger(__name__)


class BackgroundQueueAdapter(IngestionQueuePort):
    def enqueue_ingestion(
        self,
        document_id: uuid.UUID,
        job_id: uuid.UUID,
        storage_uri: str,
        workspace_id: uuid.UUID,
    ) -> None:
        logger.info(
            "Enqueued ingestion job %s for document %s (workspace %s, storage %s)",
            job_id,
            document_id,
            workspace_id,
            storage_uri,
        )
