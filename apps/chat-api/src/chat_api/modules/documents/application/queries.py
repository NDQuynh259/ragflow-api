"""Document Queries and Query Handlers (Read Side)."""

from __future__ import annotations

from dataclasses import dataclass
import uuid

from chat_api.modules.documents.application.dtos import DocumentDTO, IngestionJobDTO
from chat_api.modules.documents.domain.entity import Document
from chat_api.shared.application.authorization import (
    CurrentPrincipal,
    Permission,
    require_document_access,
    require_workspace_permission,
)
from chat_api.shared.application.bus import Query, authorization_handler, query_handler
from chat_api.shared.domain.uow import UnitOfWork
from chat_api.shared.exceptions import EntityNotFoundException


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
        doc = self.uow.documents.get_by_id(query.document_id)
        if not doc:
            raise EntityNotFoundException("Document", query.document_id)
        return self._to_dto(doc)

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
        docs = self.uow.documents.list_by_workspace(
            workspace_id=query.workspace_id,
            limit=query.limit,
            offset=query.offset,
        )
        handler = GetDocumentHandler(self.uow)
        return [handler._to_dto(d) for d in docs]
