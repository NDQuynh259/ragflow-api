"""Upload Document Command and Handler."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from chat_api.modules.documents.application.dtos import DocumentDTO
from chat_api.modules.documents.application.mapper import DocumentMapper
from chat_api.modules.documents.domain.entity import Document, DocumentStatus
from chat_api.modules.documents.domain.events import DocumentIngestionRequested
from chat_api.modules.documents.domain.repository import DocumentRepository
from chat_api.modules.documents.domain.value_objects import (
    ContentHash,
    Filename,
    MimeType,
    StorageUri,
)
from chat_api.modules.workspaces.domain.repository import WorkspaceRepository
from chat_api.shared.infrastructure.database import UnitOfWork
from core.cqrs import Command, command_handler
from core.exceptions import EntityNotFoundException
from core.storage import FileUploader, ObjectStoragePort
from core.uuid7 import uuid7


@dataclass(frozen=True)
class UploadDocumentCommand(Command[DocumentDTO]):
    workspace_id: uuid.UUID
    filename: str
    content: bytes
    mime_type: str = "application/pdf"
    parser_name: str = "opendataloader"
    chunker_name: str = "heading_aware"
    uploaded_by: uuid.UUID | None = None


@command_handler(UploadDocumentCommand)
class UploadDocumentHandler:
    def __init__(
        self,
        uow: UnitOfWork,
        storage: ObjectStoragePort,
        uploader: FileUploader | None = None,
    ) -> None:
        self.uow = uow
        self.storage = storage
        self.uploader = uploader or FileUploader(storage=storage)

    def handle(self, cmd: UploadDocumentCommand) -> DocumentDTO:
        validated = self.uploader.validator.validate(
            filename=cmd.filename,
            content=cmd.content,
            declared_mime_type=cmd.mime_type,
        )
        content_hash = ContentHash(validated.content_hash)

        workspace_repo = self.uow.get_repo(WorkspaceRepository)
        doc_repo = self.uow.get_repo(DocumentRepository)

        workspace = workspace_repo.get_by_id(cmd.workspace_id)
        if not workspace:
            raise EntityNotFoundException("Workspace", cmd.workspace_id)

        existing = doc_repo.get_by_content_hash(cmd.workspace_id, content_hash)
        if existing:
            return DocumentMapper.to_dto(existing)

        raw_uri = self.storage.save(validated.filename, validated.content, cmd.workspace_id)
        document = Document(
            id=uuid7(),
            workspace_id=cmd.workspace_id,
            filename=Filename(validated.filename),
            storage_uri=StorageUri(raw_uri),
            content_hash=content_hash,
            mime_type=MimeType(validated.detected_mime_type),
            file_size=validated.file_size,
            status=DocumentStatus.QUEUED,
        )
        job = document.create_ingestion_job(
            parser_name=cmd.parser_name,
            chunker_name=cmd.chunker_name,
        )

        doc_repo.save(document)
        document.record_event(
            DocumentIngestionRequested(
                document_id=document.id,
                job_id=job.id,
                storage_uri=str(document.storage_uri),
                workspace_id=cmd.workspace_id,
                user_id=cmd.uploaded_by,
            )
        )
        self.uow.track(document)
        return DocumentMapper.to_dto(document)
