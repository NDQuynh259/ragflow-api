"""Document Queries and Query Handlers (Read Side)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from chat_api.modules.documents.application.dtos import DocumentDTO
from chat_api.modules.documents.application.mapper import DocumentMapper
from chat_api.modules.documents.domain.repository import DocumentRepository
from chat_api.shared.infrastructure.database import UnitOfWork
from core.cqrs import Query, query_handler
from core.exceptions import EntityNotFoundException


@dataclass(frozen=True)
class GetDocumentQuery(Query[DocumentDTO]):
    document_id: uuid.UUID


@query_handler(GetDocumentQuery)
class GetDocumentHandler:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    def handle(self, query: GetDocumentQuery) -> DocumentDTO:
        doc_repo = self.uow.get_repo(DocumentRepository)
        doc = doc_repo.get_by_id(query.document_id)
        if not doc:
            raise EntityNotFoundException("Document", query.document_id)
        return DocumentMapper.to_dto(doc)


@dataclass(frozen=True)
class ListDocumentsQuery(Query[list[DocumentDTO]]):
    workspace_id: uuid.UUID
    limit: int = 50
    offset: int = 0


@query_handler(ListDocumentsQuery)
class ListDocumentsHandler:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    def handle(self, query: ListDocumentsQuery) -> list[DocumentDTO]:
        doc_repo = self.uow.get_repo(DocumentRepository)
        docs = doc_repo.list_by_workspace(
            workspace_id=query.workspace_id,
            limit=query.limit,
            offset=query.offset,
        )
        return [DocumentMapper.to_dto(d) for d in docs]
