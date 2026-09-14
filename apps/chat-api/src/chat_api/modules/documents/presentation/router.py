"""Documents REST router."""

from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, File, Query, UploadFile, status

from chat_api.modules.documents.application.commands import (
    DeleteDocumentCommand,
    DeleteDocumentHandler,
    UploadDocumentCommand,
    UploadDocumentHandler,
)
from chat_api.modules.documents.application.queries import (
    GetDocumentHandler,
    GetDocumentQuery,
    ListDocumentsHandler,
    ListDocumentsQuery,
)
from chat_api.modules.documents.presentation.dtos import (
    DocumentResponse,
    UploadDocumentResponse,
)
from chat_api.shared.domain.uow import UnitOfWork
from chat_api.shared.infrastructure.database.uow import get_uow
from chat_api.shared.infrastructure.queue.background import BackgroundQueueAdapter
from chat_api.shared.infrastructure.queue.port import IngestionQueuePort
from chat_api.shared.infrastructure.storage.local import LocalStorageAdapter
from chat_api.shared.infrastructure.storage.port import ObjectStoragePort

router = APIRouter(tags=["Documents"])

_storage = LocalStorageAdapter()
_queue = BackgroundQueueAdapter()


def get_storage() -> ObjectStoragePort:
    return _storage


def get_queue() -> IngestionQueuePort:
    return _queue


@router.post(
    "/workspaces/{workspace_id}/documents",
    response_model=UploadDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_workspace_document(
    workspace_id: uuid.UUID,
    file: UploadFile = File(...),
    uow: UnitOfWork = Depends(get_uow),
    storage: ObjectStoragePort = Depends(get_storage),
    queue: IngestionQueuePort = Depends(get_queue),
) -> UploadDocumentResponse:
    content = await file.read()
    cmd = UploadDocumentCommand(
        workspace_id=workspace_id,
        filename=file.filename or "document.pdf",
        content=content,
        mime_type=file.content_type or "application/pdf",
    )
    doc_dto = UploadDocumentHandler(uow, storage, queue).handle(cmd)
    return UploadDocumentResponse(document=doc_dto.__dict__)


@router.get("/documents/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: uuid.UUID,
    uow: UnitOfWork = Depends(get_uow),
) -> DocumentResponse:
    query = GetDocumentQuery(document_id=document_id)
    result = GetDocumentHandler(uow).handle(query)
    return DocumentResponse(**result.__dict__)


@router.get("/workspaces/{workspace_id}/documents", response_model=list[DocumentResponse])
def list_workspace_documents(
    workspace_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    uow: UnitOfWork = Depends(get_uow),
) -> list[DocumentResponse]:
    query = ListDocumentsQuery(workspace_id=workspace_id, limit=limit, offset=offset)
    results = ListDocumentsHandler(uow).handle(query)
    return [DocumentResponse(**r.__dict__) for r in results]


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: uuid.UUID,
    uow: UnitOfWork = Depends(get_uow),
    storage: ObjectStoragePort = Depends(get_storage),
) -> None:
    cmd = DeleteDocumentCommand(document_id=document_id)
    DeleteDocumentHandler(uow, storage).handle(cmd)
