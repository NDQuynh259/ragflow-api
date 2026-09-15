"""Authentication CQRS Commands and Handlers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from chat_api.modules.auth.domain.entity import UserSession
from chat_api.modules.auth.infrastructure.security import (
    generate_session_token,
    hash_password,
    verify_password,
)
from chat_api.modules.users.domain.entity import User
from chat_api.modules.workspaces.domain.entity import (
    Workspace,
    WorkspaceMember,
    WorkspaceRole,
)
from chat_api.shared.domain.uow import UnitOfWork
from core.exceptions import (
    DomainValidationException,
    EntityNotFoundException,
    ResourceConflictException,
    UnauthorizedException,
)

DEFAULT_SESSION_DURATION_DAYS = 7


@dataclass(frozen=True)
class RegisterCommand:
    email: str
    password: str
    full_name: str | None = None


class RegisterHandler:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    def handle(self, command: RegisterCommand) -> User:
        clean_email = command.email.strip().lower()
        if not clean_email or "@" not in clean_email:
            raise DomainValidationException("Invalid email format.")
        if len(command.password) < 6:
            raise DomainValidationException("Password must be at least 6 characters long.")

        with self.uow:
            existing = self.uow.users.get_by_email(clean_email)
            if existing:
                raise ResourceConflictException(f"User with email '{clean_email}' already exists.")

            user = User(
                email=clean_email,
                full_name=command.full_name.strip() if command.full_name else None,
                hashed_password=hash_password(command.password),
                is_active=True,
            )
            saved_user = self.uow.users.save(user)

            # Automatically create a default personal workspace
            clean_name = command.full_name.strip() if command.full_name else clean_email.split("@")[0]
            ws_slug = f"workspace-{saved_user.id.hex[:8]}"
            ws = Workspace(
                name=f"{clean_name}'s Workspace",
                slug=ws_slug,
                members=[],
            )
            ws.members.append(
                WorkspaceMember(
                    workspace_id=ws.id,
                    user_id=saved_user.id,
                    role=WorkspaceRole.OWNER,
                )
            )
            self.uow.workspaces.save(ws)

            self.uow.commit()
            return saved_user


@dataclass(frozen=True)
class LoginCommand:
    email: str
    password: str
    ip_address: str | None = None
    user_agent: str | None = None


@dataclass(frozen=True)
class LoginResult:
    user: User
    session: UserSession


class LoginHandler:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    def handle(self, command: LoginCommand) -> LoginResult:
        clean_email = command.email.strip().lower()
        with self.uow:
            user = self.uow.users.get_by_email(clean_email)
            if not user or not verify_password(command.password, user.hashed_password):
                raise UnauthorizedException("Invalid email or password.")

            if not user.is_active:
                raise UnauthorizedException("User account is inactive.")

            token = generate_session_token()
            expires_at = datetime.now(timezone.utc) + timedelta(days=DEFAULT_SESSION_DURATION_DAYS)

            # Auto-detect or create active workspace for user
            user_workspaces = self.uow.workspaces.list_by_user_id(user.id)
            if user_workspaces:
                active_workspace_id = user_workspaces[0].id
            else:
                clean_name = user.full_name or user.email.split("@")[0]
                ws_slug = f"workspace-{user.id.hex[:8]}"
                ws = Workspace(
                    name=f"{clean_name}'s Workspace",
                    slug=ws_slug,
                    members=[],
                )
                ws.members.append(
                    WorkspaceMember(
                        workspace_id=ws.id,
                        user_id=user.id,
                        role=WorkspaceRole.OWNER,
                    )
                )
                self.uow.workspaces.save(ws)
                active_workspace_id = ws.id

            session = UserSession(
                user_id=user.id,
                active_workspace_id=active_workspace_id,
                token=token,
                expires_at=expires_at,
                ip_address=command.ip_address,
                user_agent=command.user_agent,
            )
            self.uow.user_sessions.save(session)
            self.uow.commit()
            return LoginResult(user=user, session=session)


@dataclass(frozen=True)
class SwitchWorkspaceCommand:
    token: str
    workspace_id: uuid.UUID


class SwitchWorkspaceHandler:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    def handle(self, command: SwitchWorkspaceCommand) -> UserSession:
        with self.uow:
            session = self.uow.user_sessions.get_by_token(command.token)
            if not session or session.is_expired():
                raise UnauthorizedException("Invalid or expired session.")

            workspace = self.uow.workspaces.get_by_id(command.workspace_id)
            if not workspace:
                raise EntityNotFoundException("Workspace", command.workspace_id)

            if not workspace.is_member(session.user_id):
                raise UnauthorizedException("User is not a member of this workspace.")

            session.active_workspace_id = workspace.id
            self.uow.user_sessions.save(session)
            self.uow.commit()
            return session


@dataclass(frozen=True)
class LogoutCommand:
    token: str


class LogoutHandler:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    def handle(self, command: LogoutCommand) -> bool:
        with self.uow:
            success = self.uow.user_sessions.delete_by_token(command.token)
            self.uow.commit()
            return success
