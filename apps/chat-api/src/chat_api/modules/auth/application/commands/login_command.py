"""Login Command and Handler."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from chat_api.modules.auth.domain.entity import UserSession
from chat_api.modules.users.domain.entity import User
from chat_api.modules.workspaces.application import WorkspaceProvisioningService
from chat_api.shared.infrastructure.database import UnitOfWork
from core.cqrs import Command, command_handler
from core.exceptions import UnauthenticatedException
from core.security import (
    generate_session_token,
    verify_password,
)

DEFAULT_SESSION_DURATION_DAYS = 7


@dataclass(frozen=True)
class LoginResult:
    user: User
    session: UserSession


@dataclass(frozen=True)
class LoginCommand(Command[LoginResult]):
    email: str
    password: str
    ip_address: str | None = None
    user_agent: str | None = None


@command_handler(LoginCommand)
class LoginHandler:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    def handle(self, command: LoginCommand) -> LoginResult:
        clean_email = command.email.strip().lower()
        user = self._authenticate(clean_email, command.password)
        active_workspace_id = self._resolve_active_workspace_id(user)
        session = self._create_session(user.id, active_workspace_id, command)

        self.uow.user_sessions.save(session)
        self.uow.track(user, session)
        return LoginResult(user=user, session=session)

    def _authenticate(self, email: str, raw_password: str) -> User:
        user = self.uow.users.get_by_email(email)
        if not user or not verify_password(raw_password, user.hashed_password):
            raise UnauthenticatedException("Invalid email or password.")
        if not user.is_active:
            raise UnauthenticatedException("User account is inactive.")
        return user

    def _resolve_active_workspace_id(self, user: User) -> uuid.UUID:
        user_workspaces = self.uow.workspaces.list_by_user_id(user.id)
        if user_workspaces:
            return user_workspaces[0].id

        ws = WorkspaceProvisioningService(self.uow).create_default_workspace(user)
        return ws.id

    def _create_session(
        self,
        user_id: uuid.UUID,
        active_workspace_id: uuid.UUID,
        command: LoginCommand,
    ) -> UserSession:
        token = generate_session_token()
        expires_at = datetime.now(UTC) + timedelta(days=DEFAULT_SESSION_DURATION_DAYS)
        return UserSession(
            user_id=user_id,
            active_workspace_id=active_workspace_id,
            token=token,
            expires_at=expires_at,
            ip_address=command.ip_address,
            user_agent=command.user_agent,
        )
