"""Document Commands and Command Handlers (Write Side)."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import uuid

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
from chat_api.shared.auth import (
    CurrentPrincipal,
    Permission,
    require_document_access,
    require_workspace_permission,
)
from chat_api.shared.bus import Command, authorization_handler, command_handler
from chat_api.shared.infrastructure.database import UnitOfWork
from core.exceptions import EntityNotFoundException
from core.storage import ObjectStoragePort
from core.uuid7 import uuid7


@dataclass(frozen=True)
class UploadDocumentCommand(Command[DocumentDTO]):
    workspace_id: uuid.UUID
    filename: str
    content: bytes
    mime_type: str = "application/pdf"
    parser_name: str = "opendataloader"
    chunker_name: str = "heading_aware"


@authorization_handler(UploadDocumentCommand)
class UploadDocumentAuthorizer:
    def __init__(self, uow: UnitOfWork, principal: CurrentPrincipal) -> None:
        self.uow = uow
        self.principal = principal

    def handle(self, command: UploadDocumentCommand) -> None:
        require_workspace_permission(
            self.uow,
            self.principal,
            command.workspace_id,
            Permission.DOCUMENT_CREATE,
        )


@command_handler(UploadDocumentCommand)
class UploadDocumentHandler:
    def __init__(
        self,
        uow: UnitOfWork,
        storage: ObjectStoragePort,
    ) -> None:
        self.uow = uow
        self.storage = storage

    def handle(self, cmd: UploadDocumentCommand) -> DocumentDTO:
        content_hash = ContentHash(hashlib.sha256(cmd.content).hexdigest())

        workspace_repo = self.uow.get_repo(WorkspaceRepository)
        doc_repo = self.uow.get_repo(DocumentRepository)

        workspace = workspace_repo.get_by_id(cmd.workspace_id)
        if not workspace:
            raise EntityNotFoundException("Workspace", cmd.workspace_id)

        existing = doc_repo.get_by_content_hash(cmd.workspace_id, content_hash)
        if existing:
            return DocumentMapper.to_dto(existing)

        raw_uri = self.storage.save(cmd.filename, cmd.content, cmd.workspace_id)
        document = Document(
            id=uuid7(),
            workspace_id=cmd.workspace_id,
            filename=Filename(cmd.filename),
            storage_uri=StorageUri(raw_uri),
            content_hash=content_hash,
            mime_type=MimeType(cmd.mime_type),
            file_size=len(cmd.content),
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
            )
        )
        self.uow.track(document)
        return DocumentMapper.to_dto(document)


@dataclass(frozen=True)
class DeleteDocumentCommand(Command[bool]):
    document_id: uuid.UUID


@authorization_handler(DeleteDocumentCommand)
class DeleteDocumentAuthorizer:
    def __init__(self, uow: UnitOfWork, principal: CurrentPrincipal) -> None:
        self.uow = uow
        self.principal = principal

    def handle(self, command: DeleteDocumentCommand) -> None:
        require_document_access(
            self.uow,
            self.principal,
            command.document_id,
            Permission.DOCUMENT_DELETE,
        )


@command_handler(DeleteDocumentCommand)
class DeleteDocumentHandler:
    def __init__(self, uow: UnitOfWork, storage: ObjectStoragePort) -> None:
        self.uow = uow
        self.storage = storage

    def handle(self, cmd: DeleteDocumentCommand) -> bool:
        doc_repo = self.uow.get_repo(DocumentRepository)
        doc = doc_repo.get_by_id(cmd.document_id)
        if not doc:
            raise EntityNotFoundException("Document", cmd.document_id)

        self.storage.delete(str(doc.storage_uri))
        return doc_repo.delete(cmd.document_id)
