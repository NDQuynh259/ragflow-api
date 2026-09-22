"""Document Domain Events.

Domain events represent significant business occurrences within the Document
aggregate.  They belong to the domain layer and carry no infrastructure or
application concerns.  Event *handlers* live in the application layer.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class DocumentIngestionRequested:
    """Raised when a new document needs to be ingested by a background worker."""

    document_id: uuid.UUID
    job_id: uuid.UUID
    storage_uri: str
    workspace_id: uuid.UUID
    user_id: uuid.UUID | None = None
