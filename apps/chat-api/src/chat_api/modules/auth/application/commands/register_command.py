"""Register Command and Handler."""

from __future__ import annotations

from dataclasses import dataclass

from chat_api.modules.users.domain.entity import User
from chat_api.modules.workspaces.application import WorkspaceProvisioningService
from chat_api.shared.infrastructure.database import UnitOfWork
from core.cqrs import Command, command_handler
from core.exceptions import (
    DomainValidationException,
    ResourceConflictException,
)
from core.security import hash_password


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

        workspace_service = WorkspaceProvisioningService(self.uow)
        workspace = workspace_service.create_default_workspace(saved_user)
        self.uow.track(saved_user, workspace)
        return saved_user
