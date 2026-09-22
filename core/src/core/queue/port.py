"""Message Queue Port interfaces."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import Any

from core.uuid7 import uuid7_str


class JobQueuePort(ABC):
    """General-purpose message queue producer port for dispatching background jobs to workers."""

    @abstractmethod
    def enqueue(
        self,
        action: str,
        payload: dict[str, Any],
        job_id: str | uuid.UUID | None = None,
        routing_key: str | None = None,
        correlation_id: str | None = None,
    ) -> str:
        """Enqueue an arbitrary job action with payload, returning the unique job_id."""
        pass

    def check_health(self) -> bool:
        """Check if message queue broker connection is healthy."""
        return True

    def close(self) -> None:
        """Release underlying broker connections."""
        pass


class IngestionQueuePort(JobQueuePort):
    """Specialized queue port for document ingestion jobs.

    100% backward compatible with existing chat-api router and event handlers.
    Provides a concrete fallback for enqueue() so any test fake or subclass implementing
    only enqueue_ingestion() can still be instantiated cleanly.
    """

    def enqueue(
        self,
        action: str,
        payload: dict[str, Any],
        job_id: str | uuid.UUID | None = None,
        routing_key: str | None = None,
        correlation_id: str | None = None,
    ) -> str:
        """Default fallback routing to enqueue_ingestion for index/reindex actions."""
        resolved_job_id = str(job_id) if job_id else uuid7_str()
        if (
            action in ("index", "reindex")
            and "document_id" in payload
            and "workspace_id" in payload
        ):
            kwargs: dict[str, Any] = {
                "document_id": uuid.UUID(str(payload["document_id"])),
                "job_id": uuid.UUID(resolved_job_id),
                "storage_uri": str(payload.get("storage_uri", "")),
                "workspace_id": uuid.UUID(str(payload["workspace_id"])),
            }
            import inspect

            if "user_id" in inspect.signature(self.enqueue_ingestion).parameters:
                kwargs["user_id"] = (
                    uuid.UUID(str(payload["user_id"])) if payload.get("user_id") else None
                )
            self.enqueue_ingestion(**kwargs)
        return resolved_job_id

    @abstractmethod
    def enqueue_ingestion(
        self,
        document_id: uuid.UUID,
        job_id: uuid.UUID,
        storage_uri: str,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
    ) -> None:
        """Publish document ingestion job to background worker queue."""
        pass


__all__ = ["IngestionQueuePort", "JobQueuePort"]
