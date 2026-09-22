"""Application DTOs for Documents and Ingestion Jobs."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class IngestionJobDTO:
    id: uuid.UUID
    document_id: uuid.UUID
    status: str
    retry_count: int
    parser_name: str
    chunker_name: str
    elapsed_seconds: float | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass(frozen=True)
class DocumentDTO:
    id: uuid.UUID
    workspace_id: uuid.UUID
    filename: str
    content_hash: str
    mime_type: str
    file_size: int
    status: str
    error_code: str | None = None
    error_message: str | None = None
    page_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    jobs: list[IngestionJobDTO] = field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None
