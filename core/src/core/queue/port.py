"""Ingestion Queue Port interface."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod


class IngestionQueuePort(ABC):
    """Abstract port for dispatching document ingestion jobs to workers."""

    @abstractmethod
    def enqueue_ingestion(
        self,
        document_id: uuid.UUID,
        job_id: uuid.UUID,
        storage_uri: str,
        workspace_id: uuid.UUID,
    ) -> None:
        """Publish job to background worker queue."""
        pass
