"""Message Commands and Command Handlers (Write Side)."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from chat_api.modules.messages.application.dtos import MessageDTO
from chat_api.modules.messages.application.mapper import MessageMapper
from chat_api.modules.messages.domain.entity import Message, MessageRole
from chat_api.shared.infrastructure.database import UnitOfWork
from chat_api.shared.infrastructure.rag import RAGEnginePort
from core.cqrs import Command, command_handler
from core.exceptions import EntityNotFoundException
from core.uuid7 import uuid7


@dataclass(frozen=True)
class SendMessageCommand(Command[MessageDTO]):
    session_id: uuid.UUID
    content: str


@command_handler(SendMessageCommand)
class SendMessageHandler:
    def __init__(self, uow: UnitOfWork, rag_engine: RAGEnginePort) -> None:
        self.uow = uow
        self.rag_engine = rag_engine

    def handle(self, cmd: SendMessageCommand) -> MessageDTO:
        start_time = time.perf_counter()

        session = self.uow.sessions.get_by_id(cmd.session_id)
        if not session:
            raise EntityNotFoundException("ChatSession", cmd.session_id)

        ready_docs = []
        if session.attached_document_ids:
            ready_docs = self.uow.documents.get_ready_documents_by_ids(
                workspace_id=session.workspace_id,
                document_ids=session.attached_document_ids,
            )

        doc_ids_filter = [str(d.id) for d in ready_docs] if ready_docs else None
        top_k = session.rag_config.get("top_k", 5)

        user_msg = Message(
            id=uuid7(),
            session_id=cmd.session_id,
            role=MessageRole.USER,
            content=cmd.content,
        )
        self.uow.messages.save(user_msg)

        answer, raw_citations, usage = self.rag_engine.answer(
            query=cmd.content,
            document_ids=doc_ids_filter,
            top_k=top_k,
        )

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        assistant_msg = Message(
            id=uuid7(),
            session_id=cmd.session_id,
            role=MessageRole.ASSISTANT,
            content=answer,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            latency_ms=round(latency_ms, 2),
        )

        for citation in raw_citations:
            try:
                citation_document_id = uuid.UUID(citation["document_id"])
            except (ValueError, KeyError):
                continue

            assistant_msg.add_citation(
                chunk_id=citation.get("chunk_id", ""),
                document_id=citation_document_id,
                page_number=citation.get("page_number", 1),
                bbox=citation.get("bbox") or [],
                quote=citation.get("quote"),
                relevance_score=citation.get("relevance_score"),
            )

        self.uow.messages.save(assistant_msg)
        self.uow.track(user_msg, assistant_msg)

        return MessageMapper.to_dto(assistant_msg)
