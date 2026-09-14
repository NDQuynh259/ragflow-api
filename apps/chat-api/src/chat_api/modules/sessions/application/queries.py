"""Chat Session Queries and Query Handlers (Read Side)."""

from __future__ import annotations

from dataclasses import dataclass
import uuid

from chat_api.modules.sessions.application.dtos import SessionDTO
from chat_api.shared.domain.uow import UnitOfWork
from chat_api.shared.exceptions import EntityNotFoundException


@dataclass(frozen=True)
class GetSessionQuery:
    session_id: uuid.UUID


class GetSessionHandler:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    def handle(self, query: GetSessionQuery) -> SessionDTO:
        with self.uow:
            session = self.uow.sessions.get_by_id(query.session_id)
            if not session:
                raise EntityNotFoundException("ChatSession", query.session_id)

            return SessionDTO(
                id=session.id,
                workspace_id=session.workspace_id,
                user_id=session.user_id,
                title=session.title,
                rag_config=session.rag_config,
                attached_document_ids=session.attached_document_ids,
                created_at=session.created_at,
                updated_at=session.updated_at,
            )


@dataclass(frozen=True)
class ListSessionsQuery:
    workspace_id: uuid.UUID
    user_id: uuid.UUID | None = None
    limit: int = 50
    offset: int = 0


class ListSessionsHandler:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    def handle(self, query: ListSessionsQuery) -> list[SessionDTO]:
        with self.uow:
            sessions = self.uow.sessions.list_by_workspace(
                workspace_id=query.workspace_id,
                user_id=query.user_id,
                limit=query.limit,
                offset=query.offset,
            )
            return [
                SessionDTO(
                    id=s.id,
                    workspace_id=s.workspace_id,
                    user_id=s.user_id,
                    title=s.title,
                    rag_config=s.rag_config,
                    attached_document_ids=s.attached_document_ids,
                    created_at=s.created_at,
                    updated_at=s.updated_at,
                )
                for s in sessions
            ]
