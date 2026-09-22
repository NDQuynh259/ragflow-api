"""Chat Session Queries and Query Handlers (Read Side)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from chat_api.modules.chat_sessions.application.dtos import SessionDTO
from chat_api.modules.chat_sessions.application.mapper import SessionMapper
from chat_api.shared.infrastructure.database import UnitOfWork
from core.cqrs import Query, query_handler
from core.exceptions import EntityNotFoundException


@dataclass(frozen=True)
class GetSessionQuery(Query[SessionDTO]):
    session_id: uuid.UUID


@query_handler(GetSessionQuery)
class GetSessionHandler:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    def handle(self, query: GetSessionQuery) -> SessionDTO:
        session = self.uow.sessions.get_by_id(query.session_id)
        if not session:
            raise EntityNotFoundException("ChatSession", query.session_id)

        return SessionMapper.to_dto(session)


@dataclass(frozen=True)
class ListSessionsQuery(Query[list[SessionDTO]]):
    workspace_id: uuid.UUID
    user_id: uuid.UUID | None = None
    limit: int = 50
    offset: int = 0


@query_handler(ListSessionsQuery)
class ListSessionsHandler:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    def handle(self, query: ListSessionsQuery) -> list[SessionDTO]:
        sessions = self.uow.sessions.list_by_workspace(
            workspace_id=query.workspace_id,
            user_id=query.user_id,
            limit=query.limit,
            offset=query.offset,
        )
        return [SessionMapper.to_dto(s) for s in sessions]
