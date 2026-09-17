"""Switch Workspace Command and Handler."""

from __future__ import annotations

from dataclasses import dataclass
import uuid

from chat_api.modules.auth.domain.entity import UserSession
from chat_api.shared.bus import Command, command_handler
from chat_api.shared.database import UnitOfWork
from core.exceptions import (
    EntityNotFoundException,
    ForbiddenException,
    UnauthenticatedException,
)


@dataclass(frozen=True)
class SwitchWorkspaceCommand(Command[UserSession]):
    token: str
    workspace_id: uuid.UUID


@command_handler(SwitchWorkspaceCommand)
class SwitchWorkspaceHandler:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    def handle(self, command: SwitchWorkspaceCommand) -> UserSession:
        session = self.uow.user_sessions.get_by_token(command.token)
        if not session or session.is_expired():
            raise UnauthenticatedException("Invalid or expired session.")

        workspace = self.uow.workspaces.get_by_id(command.workspace_id)
        if not workspace:
            raise EntityNotFoundException("Workspace", command.workspace_id)

        if not workspace.is_member(session.user_id):
            raise ForbiddenException("User is not a member of this workspace.")

        session.active_workspace_id = workspace.id
        self.uow.user_sessions.save(session)
        self.uow.track(session)
        return session
