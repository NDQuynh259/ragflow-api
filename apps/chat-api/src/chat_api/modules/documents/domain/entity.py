"""Document Domain Aggregate and Ingestion Entities."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import uuid

from chat_api.shared.domain.base_entity import AggregateRoot, Entity
from chat_api.shared.domain.uuid7 import uuid7


class DocumentStatus(str, Enum):
    UPLOADED = "uploaded"
    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class IngestionStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(kw_only=True)
class IngestionJob(Entity[uuid.UUID]):
    id: uuid.UUID = field(default_factory=uuid7)
    document_id: uuid.UUID
    status: IngestionStatus = IngestionStatus.QUEUED
    retry_count: int = 0
    parser_name: str = "opendataloader"
    chunker_name: str = "heading_aware"
    elapsed_seconds: float | None = None
    error_details: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass(kw_only=True)
class Document(AggregateRoot[uuid.UUID]):
    id: uuid.UUID = field(default_factory=uuid7)
    workspace_id: uuid.UUID
    filename: str
    storage_uri: str
    content_hash: str
    mime_type: str = "application/pdf"
    file_size: int = 0
    status: DocumentStatus = DocumentStatus.QUEUED
    error_code: str | None = None
    error_message: str | None = None
    page_count: int = 0
    metadata: dict = field(default_factory=dict)
    deleted_at: datetime | None = None
    jobs: list[IngestionJob] = field(default_factory=list)

    def mark_processing(self) -> None:
        self.status = DocumentStatus.PROCESSING
        self.updated_at = datetime.now(timezone.utc)

    def mark_ready(self, page_count: int = 0) -> None:
        self.status = DocumentStatus.READY
        self.page_count = page_count
        self.error_code = None
        self.error_message = None
        self.updated_at = datetime.now(timezone.utc)

    def mark_failed(self, error_code: str, error_message: str) -> None:
        self.status = DocumentStatus.FAILED
        self.error_code = error_code
        self.error_message = error_message
        self.updated_at = datetime.now(timezone.utc)

    def create_ingestion_job(
        self,
        parser_name: str = "opendataloader",
        chunker_name: str = "heading_aware",
    ) -> IngestionJob:
        job = IngestionJob(
            id=uuid7(),
            document_id=self.id,
            status=IngestionStatus.QUEUED,
            parser_name=parser_name,
            chunker_name=chunker_name,
        )
        self.jobs.append(job)
        return job
