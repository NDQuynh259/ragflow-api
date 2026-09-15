"""Chat Session Commands and Command Handlers (Write Side)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import uuid

from chat_api.modules.sessions.application.dtos import SessionDTO
from chat_api.modules.sessions.domain.entity import ChatSession
from chat_api.shared.domain.uuid7 import uuid7
from chat_api.shared.domain.uow import UnitOfWork
from chat_api.shared.exceptions import EntityNotFoundException


@dataclass(frozen=True)
class CreateSessionCommand:
    workspace_id: uuid.UUID
    user_id: uuid.UUID | None = None
    title: str = "New Chat"
    rag_config: dict[str, Any] | None = None


class CreateSessionHandler:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    def handle(self, cmd: CreateSessionCommand) -> SessionDTO:
        with self.uow:
            workspace = self.uow.workspaces.get_by_id(cmd.workspace_id)
            if not workspace:
                raise EntityNotFoundException("Workspace", cmd.workspace_id)

            session = ChatSession(
                id=uuid7(),
                workspace_id=cmd.workspace_id,
                user_id=cmd.user_id,
                title=cmd.title.strip() or "New Chat",
                rag_config=cmd.rag_config or {"top_k": 5, "rerank": True},
            )
            self.uow.sessions.save(session)
            self.uow.commit()

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
class AttachDocumentCommand:
    session_id: uuid.UUID
    document_id: uuid.UUID


class AttachDocumentHandler:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    def handle(self, cmd: AttachDocumentCommand) -> SessionDTO:
        with self.uow:
            session = self.uow.sessions.get_by_id(cmd.session_id)
            if not session:
                raise EntityNotFoundException("ChatSession", cmd.session_id)

            document = self.uow.documents.get_by_id(cmd.document_id)
            if not document or document.workspace_id != session.workspace_id:
                raise EntityNotFoundException("Document", cmd.document_id)

            session.attach_document(cmd.document_id)
            self.uow.sessions.save(session)
            self.uow.commit()

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
class DeleteSessionCommand:
    session_id: uuid.UUID


class DeleteSessionHandler:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    def handle(self, cmd: DeleteSessionCommand) -> bool:
        with self.uow:
            deleted = self.uow.sessions.delete(cmd.session_id)
            self.uow.commit()
            return deleted
