"""Documents REST router."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Query, UploadFile, status

from chat_api.composition.dependencies import get_queue, get_storage
from chat_api.modules.documents.application.commands import (
    DeleteDocumentCommand,
    UploadDocumentCommand,
)
from chat_api.modules.documents.application.queries import (
    GetDocumentQuery,
    ListDocumentsQuery,
)
from chat_api.modules.documents.presentation.dtos import (
    DocumentResponse,
    UploadDocumentResponse,
)
from chat_api.shared.auth import (
    CurrentAuth,
    Permission,
    RequireAuth,
    RequirePermission,
    auth_openapi,
)
from core.queue.port import IngestionQueuePort
from core.storage import ObjectStoragePort

router = APIRouter(
    prefix="/documents",
    tags=["Documents"],
    dependencies=[Depends(RequireAuth())],
)


# region upload_document
@router.post(
    "",
    response_model=UploadDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a new document",
    dependencies=[Depends(RequirePermission(Permission.DOCUMENT_CREATE))],
    openapi_extra=auth_openapi(Permission.DOCUMENT_CREATE),
)
async def upload_document(
    auth: CurrentAuth,
    file: UploadFile = File(...),
    storage: ObjectStoragePort = Depends(get_storage),
    queue: IngestionQueuePort = Depends(get_queue),
) -> UploadDocumentResponse:
    content = await file.read()
    cmd = UploadDocumentCommand(
        workspace_id=auth.active_workspace_id,
        filename=file.filename or "document.pdf",
        content=content,
        mime_type=file.content_type or "application/pdf",
        uploaded_by=auth.principal.user_id,
    )
    doc_dto = auth.command_bus.execute(
        cmd,
        dependencies={
            ObjectStoragePort: storage,
            IngestionQueuePort: queue,
        },
    )
    return UploadDocumentResponse(document=DocumentResponse.model_validate(doc_dto))


# endregion


# region list_documents
@router.get(
    "",
    response_model=list[DocumentResponse],
    summary="List documents in active workspace",
    dependencies=[Depends(RequirePermission(Permission.DOCUMENT_READ))],
    openapi_extra=auth_openapi(Permission.DOCUMENT_READ),
)
def list_documents(
    auth: CurrentAuth,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[DocumentResponse]:
    query = ListDocumentsQuery(workspace_id=auth.active_workspace_id, limit=limit, offset=offset)
    results = auth.query_bus.execute(query)
    return [DocumentResponse.model_validate(r) for r in results]


# endregion


# region get_document
@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Get document details by ID",
    dependencies=[Depends(RequirePermission(Permission.DOCUMENT_READ))],
    openapi_extra=auth_openapi(Permission.DOCUMENT_READ),
)
def get_document(
    document_id: uuid.UUID,
    auth: CurrentAuth,
) -> DocumentResponse:
    query = GetDocumentQuery(document_id=document_id)
    result = auth.query_bus.execute(query)
    return DocumentResponse.model_validate(result)


# endregion


# region delete_document
@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document by ID",
    dependencies=[Depends(RequirePermission(Permission.DOCUMENT_DELETE))],
    openapi_extra=auth_openapi(Permission.DOCUMENT_DELETE),
)
def delete_document(
    document_id: uuid.UUID,
    auth: CurrentAuth,
    storage: ObjectStoragePort = Depends(get_storage),
) -> None:
    cmd = DeleteDocumentCommand(document_id=document_id)
    auth.command_bus.execute(
        cmd,
        dependencies={ObjectStoragePort: storage},
    )


# endregion
