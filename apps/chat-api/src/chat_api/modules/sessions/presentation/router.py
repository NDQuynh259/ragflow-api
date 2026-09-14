"""Chat Sessions REST router."""

from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, File, Query, UploadFile, status

from chat_api.modules.documents.application.commands import (
    UploadDocumentCommand,
    UploadDocumentHandler,
)
from chat_api.modules.documents.presentation.dtos import UploadDocumentResponse
from chat_api.modules.sessions.application.commands import (
    AttachDocumentCommand,
    AttachDocumentHandler,
    CreateSessionCommand,
    CreateSessionHandler,
    DeleteSessionCommand,
    DeleteSessionHandler,
)
from chat_api.modules.sessions.application.queries import (
    GetSessionHandler,
    GetSessionQuery,
    ListSessionsHandler,
    ListSessionsQuery,
)
from chat_api.modules.sessions.presentation.dtos import (
    AttachDocumentRequest,
    CreateSessionRequest,
    SessionResponse,
)
from chat_api.shared.domain.uow import UnitOfWork
from chat_api.shared.infrastructure.database.uow import get_uow
from chat_api.shared.infrastructure.queue.background import BackgroundQueueAdapter
from chat_api.shared.infrastructure.queue.port import IngestionQueuePort
from chat_api.shared.infrastructure.storage.local import LocalStorageAdapter
from chat_api.shared.infrastructure.storage.port import ObjectStoragePort

router = APIRouter(prefix="/chat-sessions", tags=["Chat Sessions"])

_storage = LocalStorageAdapter()
_queue = BackgroundQueueAdapter()


def get_storage() -> ObjectStoragePort:
    return _storage


def get_queue() -> IngestionQueuePort:
    return _queue


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
def create_session(
    payload: CreateSessionRequest,
    uow: UnitOfWork = Depends(get_uow),
) -> SessionResponse:
    cmd = CreateSessionCommand(
        workspace_id=payload.workspace_id,
        user_id=payload.user_id,
        title=payload.title,
        rag_config=payload.rag_config,
    )
    result = CreateSessionHandler(uow).handle(cmd)
    return SessionResponse(**result.__dict__)


@router.get("", response_model=list[SessionResponse])
def list_sessions(
    workspace_id: uuid.UUID = Query(..., description="Workspace ID"),
    user_id: uuid.UUID | None = Query(None, description="Filter by User ID"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    uow: UnitOfWork = Depends(get_uow),
) -> list[SessionResponse]:
    query = ListSessionsQuery(
        workspace_id=workspace_id,
        user_id=user_id,
        limit=limit,
        offset=offset,
    )
    results = ListSessionsHandler(uow).handle(query)
    return [SessionResponse(**r.__dict__) for r in results]


@router.get("/{session_id}", response_model=SessionResponse)
def get_session(
    session_id: uuid.UUID,
    uow: UnitOfWork = Depends(get_uow),
) -> SessionResponse:
    query = GetSessionQuery(session_id=session_id)
    result = GetSessionHandler(uow).handle(query)
    return SessionResponse(**result.__dict__)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    session_id: uuid.UUID,
    uow: UnitOfWork = Depends(get_uow),
) -> None:
    cmd = DeleteSessionCommand(session_id=session_id)
    DeleteSessionHandler(uow).handle(cmd)


@router.post("/{session_id}/documents/attach", response_model=SessionResponse)
def attach_document(
    session_id: uuid.UUID,
    payload: AttachDocumentRequest,
    uow: UnitOfWork = Depends(get_uow),
) -> SessionResponse:
    cmd = AttachDocumentCommand(session_id=session_id, document_id=payload.document_id)
    result = AttachDocumentHandler(uow).handle(cmd)
    return SessionResponse(**result.__dict__)


@router.post("/{session_id}/documents", response_model=UploadDocumentResponse)
async def upload_and_attach_document(
    session_id: uuid.UUID,
    file: UploadFile = File(...),
    uow: UnitOfWork = Depends(get_uow),
    storage: ObjectStoragePort = Depends(get_storage),
    queue: IngestionQueuePort = Depends(get_queue),
) -> UploadDocumentResponse:
    session = GetSessionHandler(uow).handle(GetSessionQuery(session_id=session_id))
    content = await file.read()
    upload_cmd = UploadDocumentCommand(
        workspace_id=session.workspace_id,
        filename=file.filename or "uploaded_document.pdf",
        content=content,
        mime_type=file.content_type or "application/pdf",
    )
    doc_dto = UploadDocumentHandler(uow, storage, queue).handle(upload_cmd)

    AttachDocumentHandler(uow).handle(
        AttachDocumentCommand(session_id=session_id, document_id=doc_dto.id)
    )

    return UploadDocumentResponse(
        document=doc_dto.__dict__,
        message="Tài liệu đã được tải lên, lập job xử lý và gắn vào phiên chat.",
    )
