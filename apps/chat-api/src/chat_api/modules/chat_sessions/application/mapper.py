"""Centralised Domain → DTO mapping for the Chat Sessions module."""

from __future__ import annotations

from chat_api.modules.chat_sessions.application.dtos import SessionDTO
from chat_api.modules.chat_sessions.domain.entity import ChatSession


class SessionMapper:
    """Maps ChatSession aggregate → SessionDTO."""

    @staticmethod
    def to_dto(session: ChatSession) -> SessionDTO:
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
