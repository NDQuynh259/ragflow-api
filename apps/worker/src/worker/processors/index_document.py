"""Document indexing processor for background queue worker."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from worker.bus import get_worker_command_bus
from worker.handlers.index_document import IndexDocumentCommand

logger = logging.getLogger(__name__)


def process_index_document(
    job_id: str,
    document_id: str,
    storage_uri: str,
    workspace_id: str,
    **kwargs: Any,
) -> int:
    """Worker message processor: unpacks queue message and dispatches IndexDocumentCommand via CQRS CommandBus."""
    logger.info(
        "Worker dispatching IndexDocumentCommand for document %s (job: %s)",
        document_id,
        job_id,
    )
    command = IndexDocumentCommand(
        job_id=uuid.UUID(str(job_id)),
        document_id=uuid.UUID(str(document_id)),
        workspace_id=uuid.UUID(str(workspace_id)),
        storage_uri=str(storage_uri),
    )

    bus = get_worker_command_bus()
    return bus.execute(command)


__all__ = ["process_index_document"]
