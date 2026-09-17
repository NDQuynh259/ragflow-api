"""FastAPI authentication dependencies and request-scoped security guards."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated
import uuid

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

if TYPE_CHECKING:
    from chat_api.modules.auth.domain.entity import UserSession
    from chat_api.modules.users.domain.entity import User

from chat_api.shared.auth.permissions import (
    CurrentPrincipal,
    ExecutionContext,
    Permission,
)
from chat_api.shared.bus import CommandBus, QueryBus
from chat_api.shared.database.uow import UnitOfWork, get_uow
from core.exceptions import ForbiddenException, UnauthenticatedException

bearer_scheme = HTTPBearer(auto_error=False)


def api_cookie_auth(name: str = "session") -> dict[str, object]:
    """Describe Cookie authentication in OpenAPI matching ViShop's @ApiCookieAuth('session')."""
    return {
        "security": [{name: []}, {"bearerAuth": []}],
    }


def api_workspace_header() -> dict[str, object]:
    """Describe X-Workspace-Id header in OpenAPI matching ViShop's @ApiTenantHeader()."""
    return {
        "parameters": [
            {
                "name": "X-Workspace-Id",
                "in": "header",
                "required": False,
                "schema": {"type": "string", "format": "uuid"},
                "description": "Workspace ID (tương đương X-Tenant-Id bên ViShop)",
            }
        ]
    }


def auth_openapi(*permissions: str | Permission, cookie_scheme: str = "session") -> dict[str, object]:
    """Describe authentication, cookie session, and permission requirements in OpenAPI."""
    return {
        "security": [{cookie_scheme: []}, {"bearerAuth": []}],
        "x-authentication-required": True,
        "x-permission-mode": "all",
        "x-required-permissions": [
            permission.value if isinstance(permission, Permission) else str(permission)
            for permission in permissions
        ],
    }


def extract_session_token(
    request: Request,
    bearer_auth: HTTPAuthorizationCredentials | None = None,
) -> str | None:
    """Extract a session token from cookie or supported authorization headers."""
    token = request.cookies.get("session_token")
    if token:
        return token

    if bearer_auth and bearer_auth.credentials:
        return bearer_auth.credentials

    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    x_token = request.headers.get("X-Session-Token")
    if x_token:
        return x_token.strip()
    return None


@dataclass(frozen=True, slots=True)
class AuthContext:
    user: User
    session: UserSession
    principal: CurrentPrincipal
    command_bus: CommandBus
    query_bus: QueryBus
    uow: UnitOfWork


def get_auth_context(
    request: Request,
    bearer_auth: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    uow: UnitOfWork = Depends(get_uow),
) -> AuthContext:
    token = extract_session_token(request, bearer_auth)
    if not token:
        raise UnauthenticatedException("Authentication credentials were not provided.")
    from chat_api.modules.auth.application.queries import GetAuthenticationContextQuery

    authentication = QueryBus(uow).execute(GetAuthenticationContextQuery(token=token))
    execution = ExecutionContext(principal=authentication.principal)
    return AuthContext(
        user=authentication.user,
        session=authentication.session,
        principal=authentication.principal,
        command_bus=CommandBus(uow=uow, execution_context=execution),
        query_bus=QueryBus(uow=uow, execution_context=execution),
        uow=uow,
    )


def get_current_principal(auth: AuthContext = Depends(get_auth_context)) -> CurrentPrincipal:
    """Fast dependency for endpoints only needing security principal/permissions."""
    return auth.principal


# Clean, expressive authentication dependencies
CurrentAuth = Annotated[AuthContext, Depends(get_auth_context)]
CurrentPrincipalDep = Annotated[CurrentPrincipal, Depends(get_current_principal)]

# Backward compatibility alias
AuthDep = CurrentAuth


async def resolve_target_workspace_id(
    request: Request | None,
    auth: AuthContext,
) -> uuid.UUID | None:
    """Resolve target workspace ID from path parameter, header, query parameter, body, or session."""
    if request is None:
        return auth.principal.active_workspace_id or auth.session.active_workspace_id

    # 1. Direct workspace_id in path parameters (/workspaces/{workspace_id}/...)
    ws_param = request.path_params.get("workspace_id")
    if ws_param:
        try:
            return uuid.UUID(str(ws_param))
        except ValueError:
            pass

    # 2. Workspace ID in header (X-Workspace-Id)
    ws_header = request.headers.get("X-Workspace-Id")
    if ws_header:
        try:
            return uuid.UUID(ws_header.strip())
        except ValueError:
            pass

    # 3. Query parameter (?workspace_id=...)
    ws_query = request.query_params.get("workspace_id")
    if ws_query:
        try:
            return uuid.UUID(ws_query.strip())
        except ValueError:
            pass

    # 4. Resolve from document_id in path if present
    doc_param = request.path_params.get("document_id")
    if doc_param and auth.uow:
        try:
            doc = auth.uow.documents.get_by_id(uuid.UUID(str(doc_param)))
            if doc:
                return doc.workspace_id
        except (ValueError, AttributeError):
            pass

    # 5. Resolve from session_id in path if present
    session_param = request.path_params.get("session_id")
    if session_param and auth.uow:
        try:
            s = auth.uow.chat_sessions.get_by_id(uuid.UUID(str(session_param)))
            if s:
                return s.workspace_id
        except (ValueError, AttributeError):
            pass

    # 6. Resolve from JSON request body if present (e.g. POST /chat-sessions {"workspace_id": ...})
    if request.method in ("POST", "PUT", "PATCH"):
        try:
            body_bytes = await request.body()
            if body_bytes:
                import json
                body_json = json.loads(body_bytes)
                if isinstance(body_json, dict) and "workspace_id" in body_json:
                    return uuid.UUID(str(body_json["workspace_id"]))
        except Exception:
            pass

    # 7. Fall back to current active workspace in session
    return auth.principal.active_workspace_id or auth.session.active_workspace_id


class RequireAuth:
    """Dependency enforcing that caller is authenticated with a valid session (HTTP 401 if missing).

    Inspired by ViShop's @UseGuards(BetterAuthGuard) / @RequireAuth().

    Usage:
    - Route-level guard:
        @router.get("/me", dependencies=[Depends(RequireAuth())])
        # or
        @router.get("/me", dependencies=[require_auth])
    - Router-level guard (protect all routes in router):
        router = APIRouter(dependencies=[Depends(RequireAuth())])
    - Parameter dependency:
        def get_me(auth: AuthContext = Depends(RequireAuth())): ...
        # or
        def get_me(auth: CurrentAuth): ...
    """

    def __init__(self, cookie_scheme: str = "session") -> None:
        self.cookie_scheme = cookie_scheme

    async def __call__(
        self,
        auth: AuthContext = Depends(get_auth_context),
    ) -> AuthContext:
        if auth is None:
            raise UnauthenticatedException("Authentication credentials were not provided.")
        return auth

    @staticmethod
    def openapi(cookie_scheme: str = "session") -> dict[str, object]:
        """Convenience helper to attach OpenAPI security specs matching RequireAuth."""
        return auth_openapi(cookie_scheme=cookie_scheme)


require_auth = RequireAuth()
RequireAuthDep = Annotated[AuthContext, Depends(require_auth)]


class RequirePermission:
    """Dependency enforcing that caller holds ALL specified permissions (AND check).

    If principal is workspace owner, access is automatically granted.
    Supports both FastAPI dependency injection (with Request context) and direct invocation.
    """

    def __init__(self, *permissions: str | Permission) -> None:
        self.permissions = tuple(
            p.value if isinstance(p, Permission) else str(p) for p in permissions
        )

    async def __call__(
        self,
        request: Request,
        auth: AuthContext = Depends(get_auth_context),
    ) -> AuthContext:
        if isinstance(request, AuthContext):
            auth = request
            request = None  # type: ignore[assignment]

        if auth is None:
            raise UnauthenticatedException("Authentication credentials were not provided.")

        ws_id = await resolve_target_workspace_id(request, auth)
        if ws_id and auth.uow:
            role = auth.uow.workspaces.get_member_role(ws_id, auth.user.id)
            if not role:
                raise ForbiddenException("User is not a member of this workspace.")
            if role.strip().lower() == "owner":
                return auth
            perms = auth.uow.workspaces.list_permissions(ws_id, auth.user.id)
            for p in self.permissions:
                if "*" not in perms and p not in perms:
                    raise ForbiddenException(f"Missing required permission: '{p}'")
            return auth

        auth.principal.require_permission(*self.permissions)
        return auth


class RequireAnyPermission:
    """Dependency enforcing that caller holds AT LEAST ONE specified permission (OR check).

    If principal is workspace owner, access is automatically granted.
    Supports both FastAPI dependency injection (with Request context) and direct invocation.
    """

    def __init__(self, *permissions: str | Permission) -> None:
        self.permissions = tuple(
            p.value if isinstance(p, Permission) else str(p) for p in permissions
        )

    async def __call__(
        self,
        request: Request,
        auth: AuthContext = Depends(get_auth_context),
    ) -> AuthContext:
        if isinstance(request, AuthContext):
            auth = request
            request = None  # type: ignore[assignment]

        if auth is None:
            raise UnauthenticatedException("Authentication credentials were not provided.")

        ws_id = await resolve_target_workspace_id(request, auth)
        if ws_id and auth.uow:
            role = auth.uow.workspaces.get_member_role(ws_id, auth.user.id)
            if not role:
                raise ForbiddenException("User is not a member of this workspace.")
            if role.strip().lower() == "owner":
                return auth
            perms = auth.uow.workspaces.list_permissions(ws_id, auth.user.id)
            if not any("*" in perms or p in perms for p in self.permissions):
                keys = ", ".join(self.permissions)
                raise ForbiddenException(f"Missing required permission. Requires at least one of: [{keys}]")
            return auth

        auth.principal.require_any_permission(*self.permissions)
        return auth


class RequireRole:
    """Dependency enforcing that caller holds one of the specified roles."""

    def __init__(self, *roles: str) -> None:
        self.roles = tuple(r.strip().lower() for r in roles)

    async def __call__(
        self,
        request: Request,
        auth: AuthContext = Depends(get_auth_context),
    ) -> AuthContext:
        if isinstance(request, AuthContext):
            auth = request
            request = None  # type: ignore[assignment]

        if auth is None:
            raise UnauthenticatedException("Authentication credentials were not provided.")

        ws_id = await resolve_target_workspace_id(request, auth)
        if ws_id and auth.uow:
            role = auth.uow.workspaces.get_member_role(ws_id, auth.user.id)
            if not role:
                raise ForbiddenException("User is not a member of this workspace.")
            clean_role = role.strip().lower()
            if clean_role not in self.roles:
                raise ForbiddenException(f"User requires one of roles: {self.roles}, but has '{clean_role}'")
            return auth

        auth.principal.require_role(*self.roles)
        return auth


__all__ = [
    "AuthContext",
    "CurrentAuth",
    "AuthDep",
    "CurrentPrincipalDep",
    "RequireAuth",
    "RequireAuthDep",
    "require_auth",
    "RequireAnyPermission",
    "RequirePermission",
    "RequireRole",
    "api_cookie_auth",
    "api_workspace_header",
    "auth_openapi",
    "bearer_scheme",
    "extract_session_token",
    "get_auth_context",
    "get_current_principal",
    "resolve_target_workspace_id",
]
