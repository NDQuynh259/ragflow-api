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
from core.exceptions import ForbiddenException
from core.queue.port import IngestionQueuePort
from core.storage.port import ObjectStoragePort

router = APIRouter(
    prefix="/chat-sessions",
    tags=["Chat Sessions"],
    dependencies=[Depends(RequireAuth())],
)


@router.post(
    "",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RequirePermission(Permission.SESSION_CREATE))],
    openapi_extra=auth_openapi(Permission.SESSION_CREATE),
)
def create_session(
    payload: CreateSessionRequest,
    auth: CurrentAuth,
) -> SessionResponse:
    target_workspace_id = (
        payload.workspace_id
        or auth.principal.active_workspace_id
        or auth.session.active_workspace_id
    )
    if not target_workspace_id:
        raise ForbiddenException(
            "Active workspace is not set. Please switch or select an active workspace."
        )

    cmd = CreateSessionCommand(
        workspace_id=target_workspace_id,
        user_id=auth.principal.user_id,
        title=payload.title,
        rag_config=payload.rag_config,
    )
    result = auth.command_bus.execute(cmd)
    return SessionResponse(**result.__dict__)


@router.get(
    "",
    response_model=list[SessionResponse],
    dependencies=[Depends(RequirePermission(Permission.SESSION_READ))],
    openapi_extra=auth_openapi(Permission.SESSION_READ),
)
def list_sessions(
    auth: CurrentAuth,
    workspace_id: uuid.UUID | None = Query(
        None, description="Tùy chọn ghi đè Workspace ID, mặc định lấy từ active workspace"
    ),
    user_id: uuid.UUID | None = Query(None, description="Filter by User ID"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[SessionResponse]:
    target_workspace_id = (
        workspace_id or auth.principal.active_workspace_id or auth.session.active_workspace_id
    )
    if not target_workspace_id:
        raise ForbiddenException(
            "Active workspace is not set. Please switch or select an active workspace."
        )

    query = ListSessionsQuery(
        workspace_id=target_workspace_id,
        user_id=user_id,
        limit=limit,
        offset=offset,
    )
    results = auth.query_bus.execute(query)
    return [SessionResponse(**r.__dict__) for r in results]


@router.get(
    "/{session_id}",
    response_model=SessionResponse,
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


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(RequirePermission(Permission.SESSION_DELETE))],
    openapi_extra=auth_openapi(Permission.SESSION_DELETE),
)
def delete_session(
    session_id: uuid.UUID,
    auth: CurrentAuth,
) -> None:
    cmd = DeleteSessionCommand(session_id=session_id)
    auth.command_bus.execute(cmd)


@router.post(
    "/{session_id}/documents/attach",
    response_model=SessionResponse,
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


@router.post(
    "/{session_id}/documents",
    response_model=UploadDocumentResponse,
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
