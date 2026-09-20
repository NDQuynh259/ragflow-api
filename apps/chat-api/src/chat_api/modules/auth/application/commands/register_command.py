"""Register Command and Handler."""

from __future__ import annotations

from dataclasses import dataclass

from chat_api.modules.users.domain.entity import User
from chat_api.modules.workspaces.domain.entity import (
    Workspace,
    WorkspaceMember,
    WorkspaceRole,
)
from chat_api.shared.bus import Command, command_handler
from chat_api.shared.infrastructure.database import UnitOfWork
from core.security import hash_password
from core.exceptions import (
    DomainValidationException,
    ResourceConflictException,
)


@dataclass(frozen=True)
class RegisterCommand(Command[User]):
    email: str
    password: str
    full_name: str | None = None


@command_handler(RegisterCommand)
class RegisterHandler:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    def handle(self, command: RegisterCommand) -> User:
        clean_email = command.email.strip().lower()
        if not clean_email or "@" not in clean_email:
            raise DomainValidationException("Invalid email format.")
        if len(command.password) < 6:
            raise DomainValidationException("Password must be at least 6 characters long.")

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

        clean_name = command.full_name.strip() if command.full_name else clean_email.split("@")[0]
        ws_slug = f"workspace-{saved_user.id.hex[:8]}"
        workspace = Workspace(
            name=f"{clean_name}'s Workspace",
            slug=ws_slug,
            members=[],
        )
        workspace.members.append(
            WorkspaceMember(
                workspace_id=workspace.id,
                user_id=saved_user.id,
                role=WorkspaceRole.OWNER,
            )
        )
        self.uow.workspaces.save(workspace)
        self.uow.track(saved_user, workspace)
        return saved_user
