"""Application services for messages module and RAG orchestration."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from chat_api.modules.messages.domain.entity import Message, MessageRole
from core.uuid7 import uuid7

if TYPE_CHECKING:
    from chat_api.modules.chat_sessions.domain.entity import ChatSession
    from chat_api.shared.infrastructure.database import UnitOfWork
    from chat_api.shared.infrastructure.rag import RAGEnginePort


@dataclass(frozen=True)
class RAGChatResult:
    """Carries the outcome of a RAG query execution."""

    user_message: Message
    assistant_message: Message


class RAGChatOrchestratorService:
    """Orchestrates document context resolution, RAG engine query, and message/citation persistence."""

    def __init__(self, uow: UnitOfWork, rag_engine: RAGEnginePort) -> None:
        self.uow = uow
        self.rag_engine = rag_engine

    def resolve_context_document_ids(self, session: ChatSession) -> list[str] | None:
        """Resolve list of ready document IDs attached to the session."""
        if not session.attached_document_ids:
            return None

        ready_docs = self.uow.documents.get_ready_documents_by_ids(
            workspace_id=session.workspace_id,
            document_ids=session.attached_document_ids,
        )
        return [str(d.id) for d in ready_docs] if ready_docs else None

    def execute_chat(
        self,
        session: ChatSession,
        query: str,
    ) -> RAGChatResult:
        """Execute chat turn: save user query, invoke RAG engine, create assistant reply with citations."""
        start_time = time.perf_counter()

        user_msg = Message(
            id=uuid7(),
            session_id=session.id,
            role=MessageRole.USER,
            content=query,
        )
        self.uow.messages.save(user_msg)

        doc_ids_filter = self.resolve_context_document_ids(session)
        top_k = session.rag_config.get("top_k", 5)

        answer, raw_citations, usage = self.rag_engine.answer(
            query=query,
            document_ids=doc_ids_filter,
            top_k=top_k,
        )

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        assistant_msg = Message(
            id=uuid7(),
            session_id=session.id,
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

        return RAGChatResult(user_message=user_msg, assistant_message=assistant_msg)


__all__ = ["RAGChatOrchestratorService", "RAGChatResult"]
