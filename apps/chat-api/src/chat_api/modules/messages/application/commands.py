"""Message Commands and Command Handlers (Write Side)."""

from __future__ import annotations

from dataclasses import dataclass
import time
import uuid

from chat_api.modules.messages.application.dtos import CitationDTO, MessageDTO
from chat_api.modules.messages.domain.entity import Message, MessageRole
from chat_api.shared.domain.uuid7 import uuid7
from chat_api.shared.domain.uow import UnitOfWork
from chat_api.shared.exceptions import EntityNotFoundException
from chat_api.shared.infrastructure.rag.port import RAGEnginePort


@dataclass(frozen=True)
class SendMessageCommand:
    session_id: uuid.UUID
    content: str


class SendMessageHandler:
    def __init__(self, uow: UnitOfWork, rag_engine: RAGEnginePort) -> None:
        self.uow = uow
        self.rag_engine = rag_engine

    def handle(self, cmd: SendMessageCommand) -> MessageDTO:
        start_time = time.perf_counter()

        with self.uow:
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

            # 1. Save user message
            user_msg = Message(
                id=uuid7(),
                session_id=cmd.session_id,
                role=MessageRole.USER,
                content=cmd.content,
            )
            self.uow.messages.save(user_msg)

            # 2. Invoke RAG engine
            answer, raw_citations, usage = self.rag_engine.answer(
                query=cmd.content,
                document_ids=doc_ids_filter,
                top_k=top_k,
            )

            latency_ms = (time.perf_counter() - start_time) * 1000.0

            # 3. Create assistant message
            assistant_msg = Message(
                id=uuid7(),
                session_id=cmd.session_id,
                role=MessageRole.ASSISTANT,
                content=answer,
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                latency_ms=round(latency_ms, 2),
            )

            for c in raw_citations:
                try:
                    c_doc_id = uuid.UUID(c["document_id"])
                except (ValueError, KeyError):
                    continue

                assistant_msg.add_citation(
                    chunk_id=c.get("chunk_id", ""),
                    document_id=c_doc_id,
                    page_number=c.get("page_number", 1),
                    bbox=c.get("bbox") or [],
                    quote=c.get("quote"),
                    relevance_score=c.get("relevance_score"),
                )

            self.uow.messages.save(assistant_msg)
            self.uow.commit()

            return MessageDTO(
                id=assistant_msg.id,
                session_id=assistant_msg.session_id,
                role=assistant_msg.role.value,
                content=assistant_msg.content,
                prompt_tokens=assistant_msg.prompt_tokens,
                completion_tokens=assistant_msg.completion_tokens,
                latency_ms=assistant_msg.latency_ms,
                citations=[
                    CitationDTO(
                        id=cit.id,
                        message_id=cit.message_id,
                        chunk_id=cit.chunk_id,
                        document_id=cit.document_id,
                        page_number=cit.page_number,
                        bbox=cit.bbox,
                        quote=cit.quote,
                        relevance_score=cit.relevance_score,
                    )
                    for cit in assistant_msg.citations
                ],
                created_at=assistant_msg.created_at,
            )
