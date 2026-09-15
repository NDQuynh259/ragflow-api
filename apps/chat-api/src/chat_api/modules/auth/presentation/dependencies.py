"""FastAPI Authentication Dependencies."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from chat_api.modules.auth.application.queries import (
    GetCurrentUserHandler,
    GetCurrentUserQuery,
)
from chat_api.modules.users.domain.entity import User
from chat_api.shared.domain.uow import UnitOfWork
from chat_api.shared.infrastructure.database.uow import get_uow
from core.exceptions import UnauthorizedException

bearer_scheme = HTTPBearer(auto_error=False)


def extract_session_token(
    request: Request,
    bearer_auth: HTTPAuthorizationCredentials | None = None,
) -> str | None:
    """Extract session token from Cookie, Bearer Header, or X-Session-Token header."""
    # 1. Check HTTP-only cookie
    token = request.cookies.get("session_token")
    if token:
        return token

    # 2. Check Authorization: Bearer <token>
    if bearer_auth and bearer_auth.credentials:
        return bearer_auth.credentials

    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    # 3. Check X-Session-Token header
    x_token = request.headers.get("X-Session-Token")
    if x_token:
        return x_token.strip()

    return None


def get_current_user(
    request: Request,
    bearer_auth: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    uow: UnitOfWork = Depends(get_uow),
) -> User:
    """Dependency ensuring the user is authenticated via an active session."""
    token = extract_session_token(request, bearer_auth)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        handler = GetCurrentUserHandler(uow)
        return handler.handle(GetCurrentUserQuery(token=token))
    except UnauthorizedException as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_optional_current_user(
    request: Request,
    bearer_auth: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    uow: UnitOfWork = Depends(get_uow),
) -> User | None:
    """Optional authentication dependency (returns None if not logged in)."""
    token = extract_session_token(request, bearer_auth)
    if not token:
        return None

    try:
        handler = GetCurrentUserHandler(uow)
        return handler.handle(GetCurrentUserQuery(token=token))
    except UnauthorizedException:
        return None


def get_current_session(
    request: Request,
    bearer_auth: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    uow: UnitOfWork = Depends(get_uow),
) -> UserSession:
    """Dependency ensuring an active session exists."""
    token = extract_session_token(request, bearer_auth)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    with uow:
        session = uow.user_sessions.get_by_token(token)
        if not session or session.is_expired():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session is invalid or has expired.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return session


def get_current_active_workspace_id(
    session: UserSession = Depends(get_current_session),
) -> uuid.UUID:
    """Dependency ensuring user has an active workspace selected in their session."""
    if not session.active_workspace_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active workspace selected in current session.",
        )
    return session.active_workspace_id
