"""Document application event handlers.

Handlers react to domain events and orchestrate side-effects such as
enqueueing background jobs.  The domain events themselves are defined in
``documents.domain.events``.
"""

from __future__ import annotations

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
        if "user_id" in inspect.signature(self.queue.enqueue_ingestion).parameters:
            kwargs["user_id"] = event.user_id
        self.queue.enqueue_ingestion(**kwargs)
