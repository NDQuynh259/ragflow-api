"""Document Queries and Query Handlers (Read Side)."""

from __future__ import annotations

from dataclasses import dataclass
import uuid

from chat_api.modules.documents.application.dtos import DocumentDTO
from chat_api.modules.documents.application.mapper import DocumentMapper
from chat_api.modules.documents.domain.repository import DocumentRepository
from chat_api.shared.auth import (
    CurrentPrincipal,
    Permission,
    require_document_access,
    require_workspace_permission,
)
from chat_api.shared.bus import Query, authorization_handler, query_handler
from chat_api.shared.infrastructure.database import UnitOfWork
from core.exceptions import EntityNotFoundException


@dataclass(frozen=True)
class GetDocumentQuery(Query[DocumentDTO]):
    document_id: uuid.UUID


@authorization_handler(GetDocumentQuery)
class GetDocumentAuthorizer:
    def __init__(self, uow: UnitOfWork, principal: CurrentPrincipal) -> None:
        self.uow = uow
        self.principal = principal

    def handle(self, query: GetDocumentQuery) -> None:
        require_document_access(self.uow, self.principal, query.document_id)


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


@authorization_handler(ListDocumentsQuery)
class ListDocumentsAuthorizer:
    def __init__(self, uow: UnitOfWork, principal: CurrentPrincipal) -> None:
        self.uow = uow
        self.principal = principal

    def handle(self, query: ListDocumentsQuery) -> None:
        require_workspace_permission(
            self.uow,
            self.principal,
            query.workspace_id,
            Permission.DOCUMENT_READ,
        )


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
