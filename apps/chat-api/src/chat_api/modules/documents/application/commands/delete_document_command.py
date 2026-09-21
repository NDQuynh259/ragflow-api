"""Delete Document Command, Authorizer, and Handler."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from chat_api.modules.documents.domain.repository import DocumentRepository
from chat_api.shared.auth import (
    CurrentPrincipal,
    Permission,
    require_document_access,
)
from chat_api.shared.bus import Command, authorization_handler, command_handler
from chat_api.shared.infrastructure.database import UnitOfWork
from core.exceptions import EntityNotFoundException
from core.storage import ObjectStoragePort


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
