"""Chat Session Commands and Command Handlers (Write Side)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from chat_api.modules.chat_sessions.application.dtos import SessionDTO
from chat_api.modules.chat_sessions.application.mapper import SessionMapper
from chat_api.modules.chat_sessions.domain.entity import ChatSession
from chat_api.shared.auth import (
    CurrentPrincipal,
    Permission,
    require_document_access,
    require_session_access,
    require_workspace_permission,
)
from chat_api.shared.bus import Command, authorization_handler, command_handler
from chat_api.shared.infrastructure.database import UnitOfWork
from core.exceptions import EntityNotFoundException
from core.uuid7 import uuid7


@dataclass(frozen=True)
class CreateSessionCommand(Command[SessionDTO]):
    workspace_id: uuid.UUID
    user_id: uuid.UUID | None = None
    title: str = "New Chat"
    rag_config: dict[str, Any] | None = None


@authorization_handler(CreateSessionCommand)
class CreateSessionAuthorizer:
    def __init__(self, uow: UnitOfWork, principal: CurrentPrincipal) -> None:
        self.uow = uow
        self.principal = principal

    def handle(self, command: CreateSessionCommand) -> None:
        require_workspace_permission(
            self.uow,
            self.principal,
            command.workspace_id,
            Permission.SESSION_CREATE,
        )


@command_handler(CreateSessionCommand)
class CreateSessionHandler:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    def handle(self, cmd: CreateSessionCommand) -> SessionDTO:
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
        self.uow.track(session)

        return SessionMapper.to_dto(session)


@dataclass(frozen=True)
class AttachDocumentCommand(Command[SessionDTO]):
    session_id: uuid.UUID
    document_id: uuid.UUID


@authorization_handler(AttachDocumentCommand)
class AttachDocumentAuthorizer:
    def __init__(self, uow: UnitOfWork, principal: CurrentPrincipal) -> None:
        self.uow = uow
        self.principal = principal

    def handle(self, command: AttachDocumentCommand) -> None:
        require_session_access(
            self.uow,
            self.principal,
            command.session_id,
            Permission.SESSION_UPDATE,
        )
        require_document_access(
            self.uow,
            self.principal,
            command.document_id,
            Permission.DOCUMENT_READ,
        )


@command_handler(AttachDocumentCommand)
class AttachDocumentHandler:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    def handle(self, cmd: AttachDocumentCommand) -> SessionDTO:
        session = self.uow.sessions.get_by_id(cmd.session_id)
        if not session:
            raise EntityNotFoundException("ChatSession", cmd.session_id)

        document = self.uow.documents.get_by_id(cmd.document_id)
        if not document or document.workspace_id != session.workspace_id:
            raise EntityNotFoundException("Document", cmd.document_id)

        session.attach_document(cmd.document_id)
        self.uow.sessions.save(session)
        self.uow.track(session)

        return SessionMapper.to_dto(session)


@dataclass(frozen=True)
class DeleteSessionCommand(Command[bool]):
    session_id: uuid.UUID


@authorization_handler(DeleteSessionCommand)
class DeleteSessionAuthorizer:
    def __init__(self, uow: UnitOfWork, principal: CurrentPrincipal) -> None:
        self.uow = uow
        self.principal = principal

    def handle(self, command: DeleteSessionCommand) -> None:
        require_session_access(
            self.uow,
            self.principal,
            command.session_id,
            Permission.SESSION_DELETE,
        )


@command_handler(DeleteSessionCommand)
class DeleteSessionHandler:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    def handle(self, cmd: DeleteSessionCommand) -> bool:
        return self.uow.sessions.delete(cmd.session_id)
