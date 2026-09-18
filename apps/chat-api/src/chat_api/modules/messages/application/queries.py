"""Message Queries and Query Handlers (Read Side)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from chat_api.modules.messages.application.dtos import MessageDTO
from chat_api.modules.messages.application.mapper import MessageMapper
from chat_api.shared.auth import require_session_access
from chat_api.shared.bus import Query, authorization_handler, query_handler
from chat_api.shared.infrastructure.database import UnitOfWork
from core.auth import CurrentPrincipal
from core.exceptions import EntityNotFoundException


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
        return [MessageMapper.to_dto(m) for m in messages]
