"""Message Queries and Query Handlers (Read Side)."""

from __future__ import annotations

from dataclasses import dataclass
import uuid

from chat_api.modules.messages.application.dtos import CitationDTO, MessageDTO
from chat_api.modules.messages.domain.entity import Message
from chat_api.shared.application.authorization import CurrentPrincipal, require_session_access
from chat_api.shared.application.bus import Query, authorization_handler, query_handler
from chat_api.shared.domain.uow import UnitOfWork
from chat_api.shared.exceptions import EntityNotFoundException


@dataclass(frozen=True)
class GetSessionMessagesQuery(Query[list[MessageDTO]]):
    session_id: uuid.UUID
    limit: int = 100
    offset: int = 0


@authorization_handler(GetSessionMessagesQuery)
class GetSessionMessagesAuthorizer:
    def __init__(self, uow: UnitOfWork, principal: CurrentPrincipal) -> None:
        self.uow = uow
        self.principal = principal

    def handle(self, query: GetSessionMessagesQuery) -> None:
        require_session_access(self.uow, self.principal, query.session_id)


@query_handler(GetSessionMessagesQuery)
class GetSessionMessagesHandler:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    def handle(self, query: GetSessionMessagesQuery) -> list[MessageDTO]:
        session = self.uow.sessions.get_by_id(query.session_id)
        if not session:
            raise EntityNotFoundException("ChatSession", query.session_id)

        messages = self.uow.messages.list_by_session(
            session_id=query.session_id,
            limit=query.limit,
            offset=query.offset,
        )
        return [self._to_dto(m) for m in messages]

    def _to_dto(self, m: Message) -> MessageDTO:
        return MessageDTO(
            id=m.id,
            session_id=m.session_id,
            role=m.role.value if hasattr(m.role, "value") else str(m.role),
            content=m.content,
            prompt_tokens=m.prompt_tokens,
            completion_tokens=m.completion_tokens,
            latency_ms=m.latency_ms,
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
                for cit in m.citations
            ],
            created_at=m.created_at,
        )
