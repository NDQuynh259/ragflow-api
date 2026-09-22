"""Document indexing processor for background queue worker."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from worker.dependencies import get_worker_command_bus
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
    raw_user_id = kwargs.get("user_id")
    user_id = uuid.UUID(str(raw_user_id)) if raw_user_id else None

    command = IndexDocumentCommand(
        job_id=uuid.UUID(str(job_id)),
        document_id=uuid.UUID(str(document_id)),
        workspace_id=uuid.UUID(str(workspace_id)),
        storage_uri=str(storage_uri),
        user_id=user_id,
    )

    bus = get_worker_command_bus()
    return bus.execute(command)


__all__ = ["process_index_document"]
