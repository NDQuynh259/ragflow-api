"""Messages REST router."""

from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, Query

from chat_api.modules.messages.application.commands import SendMessageCommand
from chat_api.modules.messages.application.queries import GetSessionMessagesQuery
from chat_api.modules.messages.presentation.dtos import (
    CitationResponse,
    MessageResponse,
    SendMessageRequest,
)
from chat_api.modules.auth.presentation.dependencies import (
    AuthDep,
    RequirePermission,
    auth_openapi,
)
from chat_api.shared.application.authorization import Permission
from chat_api.shared.infrastructure.rag.adapter import RAGEngineAdapter
from chat_api.shared.infrastructure.rag.port import RAGEnginePort

router = APIRouter(prefix="/chat-sessions/{session_id}/messages", tags=["Messages"])

_rag_engine = RAGEngineAdapter()


def get_rag_engine() -> RAGEnginePort:
    return _rag_engine


@router.post(
    "",
    response_model=MessageResponse,
    dependencies=[Depends(RequirePermission(Permission.MESSAGE_SEND))],
    openapi_extra=auth_openapi(Permission.MESSAGE_SEND),
)
def send_message(
    session_id: uuid.UUID,
    payload: SendMessageRequest,
    auth: AuthDep,
    rag_engine: RAGEnginePort = Depends(get_rag_engine),
) -> MessageResponse:
    cmd = SendMessageCommand(session_id=session_id, content=payload.content)
    result = auth.command_bus.execute(
        cmd,
        dependencies={RAGEnginePort: rag_engine},
    )

    return MessageResponse(
        id=result.id,
        session_id=result.session_id,
        role=result.role,
        content=result.content,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        latency_ms=result.latency_ms,
        citations=[CitationResponse(**c.__dict__) for c in result.citations],
        created_at=result.created_at,
    )


@router.get(
    "",
    response_model=list[MessageResponse],
    dependencies=[Depends(RequirePermission(Permission.SESSION_READ))],
    openapi_extra=auth_openapi(Permission.SESSION_READ),
)
def get_session_messages(
    session_id: uuid.UUID,
    auth: AuthDep,
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[MessageResponse]:
    query = GetSessionMessagesQuery(session_id=session_id, limit=limit, offset=offset)
    results = auth.query_bus.execute(query)

    return [
        MessageResponse(
            id=r.id,
            session_id=r.session_id,
            role=r.role,
            content=r.content,
            prompt_tokens=r.prompt_tokens,
            completion_tokens=r.completion_tokens,
            latency_ms=r.latency_ms,
            citations=[CitationResponse(**c.__dict__) for c in r.citations],
            created_at=r.created_at,
        )
        for r in results
    ]
