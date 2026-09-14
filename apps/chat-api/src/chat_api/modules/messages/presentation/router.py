"""Messages REST router."""

from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, Query

from chat_api.modules.messages.application.commands import (
    SendMessageCommand,
    SendMessageHandler,
)
from chat_api.modules.messages.application.queries import (
    GetSessionMessagesHandler,
    GetSessionMessagesQuery,
)
from chat_api.modules.messages.presentation.dtos import (
    CitationResponse,
    MessageResponse,
    SendMessageRequest,
)
from chat_api.shared.domain.uow import UnitOfWork
from chat_api.shared.infrastructure.database.uow import get_uow
from chat_api.shared.infrastructure.rag.adapter import RAGEngineAdapter
from chat_api.shared.infrastructure.rag.port import RAGEnginePort

router = APIRouter(prefix="/chat-sessions/{session_id}/messages", tags=["Messages"])

_rag_engine = RAGEngineAdapter()


def get_rag_engine() -> RAGEnginePort:
    return _rag_engine


@router.post("", response_model=MessageResponse)
def send_message(
    session_id: uuid.UUID,
    payload: SendMessageRequest,
    uow: UnitOfWork = Depends(get_uow),
    rag_engine: RAGEnginePort = Depends(get_rag_engine),
) -> MessageResponse:
    cmd = SendMessageCommand(session_id=session_id, content=payload.content)
    result = SendMessageHandler(uow, rag_engine).handle(cmd)

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


@router.get("", response_model=list[MessageResponse])
def get_session_messages(
    session_id: uuid.UUID,
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    uow: UnitOfWork = Depends(get_uow),
) -> list[MessageResponse]:
    query = GetSessionMessagesQuery(session_id=session_id, limit=limit, offset=offset)
    results = GetSessionMessagesHandler(uow).handle(query)

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
