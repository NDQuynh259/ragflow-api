"""Logout Command and Handler."""

from __future__ import annotations

from dataclasses import dataclass

from chat_api.shared.bus import Command, command_handler
from chat_api.shared.database import UnitOfWork


@dataclass(frozen=True)
class LogoutCommand(Command[bool]):
    token: str


@command_handler(LogoutCommand)
class LogoutHandler:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    def handle(self, command: LogoutCommand) -> bool:
        return self.uow.user_sessions.delete_by_token(command.token)
