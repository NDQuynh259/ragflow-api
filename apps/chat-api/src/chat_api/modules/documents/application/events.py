"""Document application events and their in-process handlers."""

from __future__ import annotations

from dataclasses import dataclass
import uuid

from chat_api.shared.application.bus import event_handler
from chat_api.shared.infrastructure.queue.port import IngestionQueuePort


@dataclass(frozen=True)
class DocumentIngestionRequested:
    document_id: uuid.UUID
    job_id: uuid.UUID
    storage_uri: str
    workspace_id: uuid.UUID


@event_handler(DocumentIngestionRequested)
class EnqueueDocumentIngestionHandler:
    def __init__(self, queue: IngestionQueuePort) -> None:
        self.queue = queue

    def handle(self, event: DocumentIngestionRequested) -> None:
        self.queue.enqueue_ingestion(
            document_id=event.document_id,
            job_id=event.job_id,
            storage_uri=event.storage_uri,
            workspace_id=event.workspace_id,
        )
