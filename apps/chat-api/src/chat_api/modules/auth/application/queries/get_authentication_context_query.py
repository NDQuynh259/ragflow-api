"""Resolve the authenticated identity for a presented session token."""

from __future__ import annotations

from dataclasses import dataclass

from chat_api.modules.auth.domain.entity import UserSession
from chat_api.modules.users.domain.entity import User
from chat_api.shared.infrastructure.database import UnitOfWork
from core.cqrs import Query, query_handler
from core.exceptions import UnauthenticatedException
from core.security import CurrentPrincipal


@dataclass(frozen=True)
class AuthenticationContext:
    session: UserSession
    user: User
    principal: CurrentPrincipal


@dataclass(frozen=True)
class GetAuthenticationContextQuery(Query[AuthenticationContext]):
    token: str


@query_handler(GetAuthenticationContextQuery)
class GetAuthenticationContextHandler:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    def handle(self, query: GetAuthenticationContextQuery) -> AuthenticationContext:
        return resolve_authentication_context(self.uow, query.token)


def resolve_authentication_context(
    uow: UnitOfWork,
    token: str,
) -> AuthenticationContext:
    if not token:
        raise UnauthenticatedException("Authentication token is missing.")

    session = uow.user_sessions.get_by_token(token)
    if session is None or session.is_expired():
        raise UnauthenticatedException("Session is invalid or has expired.")

    user = uow.users.get_by_id(session.user_id)
    if user is None or not user.is_active:
        raise UnauthenticatedException("User account not found or inactive.")

    role: str | None = None
    permissions: frozenset[str] = frozenset()
    if session.active_workspace_id is not None:
        role = uow.workspaces.get_member_role(
            session.active_workspace_id,
            session.user_id,
        )
        permissions = uow.workspaces.list_permissions(
            session.active_workspace_id,
            session.user_id,
        )

    principal = CurrentPrincipal(
        user_id=session.user_id,
        session_id=session.id,
        active_workspace_id=session.active_workspace_id,
        role=role,
        permissions=permissions,
    )
    return AuthenticationContext(
        session=session,
        user=user,
        principal=principal,
    )
