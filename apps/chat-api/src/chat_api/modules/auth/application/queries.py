"""Authentication CQRS Queries and Handlers."""

from __future__ import annotations

from dataclasses import dataclass

from chat_api.modules.users.domain.entity import User
from chat_api.shared.domain.uow import UnitOfWork
from core.exceptions import UnauthorizedException


@dataclass(frozen=True)
class GetCurrentUserQuery:
    token: str


class GetCurrentUserHandler:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    def handle(self, query: GetCurrentUserQuery) -> User:
        if not query.token:
            raise UnauthorizedException("Authentication token is missing.")

        with self.uow:
            session = self.uow.user_sessions.get_by_token(query.token)
            if not session or session.is_expired():
                raise UnauthorizedException("Invalid or expired session.")

            user = self.uow.users.get_by_id(session.user_id)
            if not user or not user.is_active:
                raise UnauthorizedException("User account not found or inactive.")

            return user
