"""Get Current User Query and Handler."""

from __future__ import annotations

from dataclasses import dataclass

from chat_api.modules.auth.application.queries.get_authentication_context_query import (
    resolve_authentication_context,
)
from chat_api.modules.users.domain.entity import User
from chat_api.shared.infrastructure.database import UnitOfWork
from core.cqrs import Query, query_handler


@dataclass(frozen=True)
class GetCurrentUserQuery(Query[User]):
    token: str


@query_handler(GetCurrentUserQuery)
class GetCurrentUserHandler:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    def handle(self, query: GetCurrentUserQuery) -> User:
        return resolve_authentication_context(self.uow, query.token).user
