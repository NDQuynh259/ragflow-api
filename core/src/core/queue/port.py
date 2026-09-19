"""Message Queue Port interfaces."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import Any


class JobQueuePort(ABC):
    """General-purpose message queue port for dispatching background jobs to workers."""

    @abstractmethod
    def enqueue(
        self,
        action: str,
        payload: dict[str, Any],
        job_id: str | uuid.UUID | None = None,
        routing_key: str | None = None,
    ) -> str:
        """Enqueue an arbitrary job action with payload, returning the unique job_id."""
        pass


class IngestionQueuePort(JobQueuePort):
    """Specialized queue port for document ingestion jobs (100% backward compatible)."""

    @abstractmethod
    def enqueue_ingestion(
        self,
        document_id: uuid.UUID,
        job_id: uuid.UUID,
        storage_uri: str,
        workspace_id: uuid.UUID,
    ) -> None:
        """Publish document ingestion job to background worker queue."""
        pass


__all__ = ["JobQueuePort", "IngestionQueuePort"]
