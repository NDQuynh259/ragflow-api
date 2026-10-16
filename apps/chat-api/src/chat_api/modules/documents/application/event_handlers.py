"""Document application event handlers.

Handlers react to domain events and orchestrate side-effects such as
enqueueing background jobs.  The domain events themselves are defined in
``documents.domain.events``.
"""

from __future__ import annotations

import uuid
from typing import Any

from chat_api.modules.documents.domain.events import DocumentIngestionRequested
from core.cqrs import event_handler
from core.queue import IngestionQueuePort


@event_handler(DocumentIngestionRequested)
class EnqueueDocumentIngestionHandler:
    def __init__(self, queue: IngestionQueuePort) -> None:
        self.queue = queue

    def handle(self, event: DocumentIngestionRequested) -> None:
        import inspect

        kwargs: dict[str, Any] = {
            "document_id": event.document_id,
            "job_id": event.job_id,
            "storage_uri": event.storage_uri,
            "workspace_id": event.workspace_id,
        }
        parameters = inspect.signature(self.queue.enqueue_ingestion).parameters
        if "user_id" in parameters:
            kwargs["user_id"] = event.user_id
        if "document_type" in parameters:
            kwargs["document_type"] = event.document_type
        elif event.document_type is not None:
            payload = {
                key: str(value) if isinstance(value, uuid.UUID) else value
                for key, value in kwargs.items()
            }
            payload["document_type"] = event.document_type
            self.queue.enqueue("index", payload, job_id=event.job_id)
            return
        self.queue.enqueue_ingestion(**kwargs)
