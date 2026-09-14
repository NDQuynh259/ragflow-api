"""Document Commands and Command Handlers (Write Side)."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import uuid

from chat_api.modules.documents.application.dtos import DocumentDTO, IngestionJobDTO
from chat_api.modules.documents.domain.entity import Document, DocumentStatus
from chat_api.shared.domain.uow import UnitOfWork
from chat_api.shared.exceptions import EntityNotFoundException
from chat_api.shared.infrastructure.queue.port import IngestionQueuePort
from chat_api.shared.infrastructure.storage.port import ObjectStoragePort


@dataclass(frozen=True)
class UploadDocumentCommand:
    workspace_id: uuid.UUID
    filename: str
    content: bytes
    mime_type: str = "application/pdf"
    parser_name: str = "opendataloader"
    chunker_name: str = "heading_aware"


class UploadDocumentHandler:
    def __init__(
        self,
        uow: UnitOfWork,
        storage: ObjectStoragePort,
        queue: IngestionQueuePort,
    ) -> None:
        self.uow = uow
        self.storage = storage
        self.queue = queue

    def handle(self, cmd: UploadDocumentCommand) -> DocumentDTO:
        content_hash = hashlib.sha256(cmd.content).hexdigest()

        with self.uow:
            workspace = self.uow.workspaces.get_by_id(cmd.workspace_id)
            if not workspace:
                raise EntityNotFoundException("Workspace", cmd.workspace_id)

            # Idempotency check
            existing = self.uow.documents.get_by_content_hash(cmd.workspace_id, content_hash)
            if existing:
                return self._to_dto(existing)

            # Save to storage
            storage_uri = self.storage.save(cmd.filename, cmd.content, cmd.workspace_id)

            # Create document aggregate
            document = Document(
                id=uuid.uuid4(),
                workspace_id=cmd.workspace_id,
                filename=cmd.filename,
                storage_uri=storage_uri,
                content_hash=content_hash,
                mime_type=cmd.mime_type,
                file_size=len(cmd.content),
                status=DocumentStatus.QUEUED,
            )
            job = document.create_ingestion_job(
                parser_name=cmd.parser_name,
                chunker_name=cmd.chunker_name,
            )

            self.uow.documents.save(document)
            self.uow.commit()

            # Dispatch job
            self.queue.enqueue_ingestion(
                document_id=document.id,
                job_id=job.id,
                storage_uri=storage_uri,
                workspace_id=cmd.workspace_id,
            )

            return self._to_dto(document)

    def _to_dto(self, doc: Document) -> DocumentDTO:
        return DocumentDTO(
            id=doc.id,
            workspace_id=doc.workspace_id,
            filename=doc.filename,
            content_hash=doc.content_hash,
            mime_type=doc.mime_type,
            file_size=doc.file_size,
            status=doc.status.value if hasattr(doc.status, "value") else str(doc.status),
            error_code=doc.error_code,
            error_message=doc.error_message,
            page_count=doc.page_count,
            metadata=doc.metadata,
            jobs=[
                IngestionJobDTO(
                    id=j.id,
                    document_id=j.document_id,
                    status=j.status.value if hasattr(j.status, "value") else str(j.status),
                    retry_count=j.retry_count,
                    parser_name=j.parser_name,
                    chunker_name=j.chunker_name,
                    elapsed_seconds=j.elapsed_seconds,
                    started_at=j.started_at,
                    completed_at=j.completed_at,
                )
                for j in doc.jobs
            ],
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        )


@dataclass(frozen=True)
class DeleteDocumentCommand:
    document_id: uuid.UUID


class DeleteDocumentHandler:
    def __init__(self, uow: UnitOfWork, storage: ObjectStoragePort) -> None:
        self.uow = uow
        self.storage = storage

    def handle(self, cmd: DeleteDocumentCommand) -> bool:
        with self.uow:
            doc = self.uow.documents.get_by_id(cmd.document_id)
            if not doc:
                raise EntityNotFoundException("Document", cmd.document_id)

            self.storage.delete(doc.storage_uri)
            deleted = self.uow.documents.delete(cmd.document_id)
            self.uow.commit()
            return deleted
