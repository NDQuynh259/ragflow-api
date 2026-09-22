"""Delete Document Command and Handler."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from chat_api.modules.documents.domain.repository import DocumentRepository
from chat_api.shared.infrastructure.database import UnitOfWork
from core.cqrs import Command, command_handler
from core.exceptions import EntityNotFoundException
from core.storage import ObjectStoragePort


@dataclass(frozen=True)
class DeleteDocumentCommand(Command[bool]):
    document_id: uuid.UUID


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
