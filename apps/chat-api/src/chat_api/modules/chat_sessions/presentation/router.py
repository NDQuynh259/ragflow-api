"""Chat Sessions REST router."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Query, UploadFile, status

from chat_api.composition.dependencies import get_queue, get_storage
from chat_api.modules.chat_sessions.application.commands import (
    AttachDocumentCommand,
    CreateSessionCommand,
    DeleteSessionCommand,
)
from chat_api.modules.chat_sessions.application.queries import (
    GetSessionQuery,
    ListSessionsQuery,
)
from chat_api.modules.chat_sessions.presentation.dtos import (
    AttachDocumentRequest,
    CreateSessionRequest,
    SessionResponse,
)
from chat_api.modules.documents.application.commands import (
    UploadDocumentCommand,
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
    prefix="/chat-sessions",
    tags=["Chat Sessions"],
    dependencies=[Depends(RequireAuth())],
)


# region create_session
@router.post(
    "",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new chat session",
    dependencies=[Depends(RequirePermission(Permission.SESSION_CREATE))],
    openapi_extra=auth_openapi(Permission.SESSION_CREATE),
)
def create_session(
    payload: CreateSessionRequest,
    auth: CurrentAuth,
) -> SessionResponse:
    cmd = CreateSessionCommand(
        workspace_id=auth.active_workspace_id,
        user_id=auth.principal.user_id,
        title=payload.title,
        rag_config=payload.rag_config,
    )
    result = auth.command_bus.execute(cmd)
    return SessionResponse(**result.__dict__)


# endregion


# region list_sessions
@router.get(
    "",
    response_model=list[SessionResponse],
    summary="List chat sessions in active workspace",
    dependencies=[Depends(RequirePermission(Permission.SESSION_READ))],
    openapi_extra=auth_openapi(Permission.SESSION_READ),
)
def list_sessions(
    auth: CurrentAuth,
    user_id: uuid.UUID | None = Query(None, description="Filter by User ID"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[SessionResponse]:
    query = ListSessionsQuery(
        workspace_id=auth.active_workspace_id,
        user_id=user_id,
        limit=limit,
        offset=offset,
    )
    results = auth.query_bus.execute(query)
    return [SessionResponse(**r.__dict__) for r in results]


# endregion


# region get_session
@router.get(
    "/{session_id}",
    response_model=SessionResponse,
    summary="Get chat session details by ID",
    dependencies=[Depends(RequirePermission(Permission.SESSION_READ))],
    openapi_extra=auth_openapi(Permission.SESSION_READ),
)
def get_session(
    session_id: uuid.UUID,
    auth: CurrentAuth,
) -> SessionResponse:
    query = GetSessionQuery(session_id=session_id)
    result = auth.query_bus.execute(query)
    return SessionResponse(**result.__dict__)


# endregion


# region delete_session
@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a chat session by ID",
    dependencies=[Depends(RequirePermission(Permission.SESSION_DELETE))],
    openapi_extra=auth_openapi(Permission.SESSION_DELETE),
)
def delete_session(
    session_id: uuid.UUID,
    auth: CurrentAuth,
) -> None:
    cmd = DeleteSessionCommand(session_id=session_id)
    auth.command_bus.execute(cmd)


# endregion


# region attach_document
@router.post(
    "/{session_id}/documents/attach",
    response_model=SessionResponse,
    summary="Attach an existing document to session",
    dependencies=[Depends(RequirePermission(Permission.SESSION_UPDATE, Permission.DOCUMENT_READ))],
    openapi_extra=auth_openapi(
        Permission.SESSION_UPDATE,
        Permission.DOCUMENT_READ,
    ),
)
def attach_document(
    session_id: uuid.UUID,
    payload: AttachDocumentRequest,
    auth: CurrentAuth,
) -> SessionResponse:
    cmd = AttachDocumentCommand(session_id=session_id, document_id=payload.document_id)
    result = auth.command_bus.execute(cmd)
    return SessionResponse(**result.__dict__)


# endregion


# region upload_and_attach_document
@router.post(
    "/{session_id}/documents",
    response_model=UploadDocumentResponse,
    summary="Upload and attach a new document to session",
    dependencies=[
        Depends(RequirePermission(Permission.SESSION_UPDATE, Permission.DOCUMENT_CREATE))
    ],
    openapi_extra=auth_openapi(
        Permission.SESSION_READ,
        Permission.DOCUMENT_CREATE,
        Permission.SESSION_UPDATE,
        Permission.DOCUMENT_READ,
    ),
)
async def upload_and_attach_document(
    session_id: uuid.UUID,
    auth: CurrentAuth,
    file: UploadFile = File(...),
    storage: ObjectStoragePort = Depends(get_storage),
    queue: IngestionQueuePort = Depends(get_queue),
) -> UploadDocumentResponse:
    session = auth.query_bus.execute(GetSessionQuery(session_id=session_id))
    content = await file.read()
    upload_cmd = UploadDocumentCommand(
        workspace_id=session.workspace_id,
        filename=file.filename or "uploaded_document.pdf",
        content=content,
        mime_type=file.content_type or "application/pdf",
        uploaded_by=auth.principal.user_id,
    )
    doc_dto = auth.command_bus.execute(
        upload_cmd,
        dependencies={
            ObjectStoragePort: storage,
            IngestionQueuePort: queue,
        },
    )

    auth.command_bus.execute(AttachDocumentCommand(session_id=session_id, document_id=doc_dto.id))

    return UploadDocumentResponse(
        document=DocumentResponse.model_validate(doc_dto),
        message="Tài liệu đã được tải lên, lập job xử lý và gắn vào phiên chat.",
    )


# endregion
