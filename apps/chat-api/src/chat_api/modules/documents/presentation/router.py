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
from core.exceptions import ForbiddenException
from core.queue.port import IngestionQueuePort
from core.storage import ObjectStoragePort

router = APIRouter(
    prefix="/documents",
    tags=["Documents"],
    dependencies=[Depends(RequireAuth())],
)


@router.post(
    "",
    response_model=UploadDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RequirePermission(Permission.DOCUMENT_CREATE))],
    openapi_extra=auth_openapi(Permission.DOCUMENT_CREATE),
)
async def upload_document(
    auth: CurrentAuth,
    file: UploadFile = File(...),
    workspace_id: uuid.UUID | None = Query(
        None, description="Tùy chọn ghi đè Workspace ID, mặc định lấy từ active workspace"
    ),
    storage: ObjectStoragePort = Depends(get_storage),
    queue: IngestionQueuePort = Depends(get_queue),
) -> UploadDocumentResponse:
    target_workspace_id = (
        workspace_id or auth.principal.active_workspace_id or auth.session.active_workspace_id
    )
    if not target_workspace_id:
        raise ForbiddenException(
            "Active workspace is not set. Please switch or select an active workspace."
        )

    content = await file.read()
    cmd = UploadDocumentCommand(
        workspace_id=target_workspace_id,
        filename=file.filename or "document.pdf",
        content=content,
        mime_type=file.content_type or "application/pdf",
    )
    doc_dto = auth.command_bus.execute(
        cmd,
        dependencies={
            ObjectStoragePort: storage,
            IngestionQueuePort: queue,
        },
    )
    return UploadDocumentResponse(document=DocumentResponse.model_validate(doc_dto))


@router.get(
    "",
    response_model=list[DocumentResponse],
    dependencies=[Depends(RequirePermission(Permission.DOCUMENT_READ))],
    openapi_extra=auth_openapi(Permission.DOCUMENT_READ),
)
def list_documents(
    auth: CurrentAuth,
    workspace_id: uuid.UUID | None = Query(
        None, description="Tùy chọn ghi đè Workspace ID, mặc định lấy từ active workspace"
    ),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[DocumentResponse]:
    target_workspace_id = (
        workspace_id or auth.principal.active_workspace_id or auth.session.active_workspace_id
    )
    if not target_workspace_id:
        raise ForbiddenException(
            "Active workspace is not set. Please switch or select an active workspace."
        )

    query = ListDocumentsQuery(workspace_id=target_workspace_id, limit=limit, offset=offset)
    results = auth.query_bus.execute(query)
    return [DocumentResponse.model_validate(r) for r in results]


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
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


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
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
