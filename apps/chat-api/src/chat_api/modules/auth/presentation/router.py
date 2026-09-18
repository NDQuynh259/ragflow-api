"""Authentication REST Router."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status

from chat_api.modules.auth.application.commands import (
    LoginCommand,
    LogoutCommand,
    RegisterCommand,
    SwitchWorkspaceCommand,
)
from chat_api.shared.auth import (
    CurrentAuth,
    RequireAuth,
    auth_openapi,
    extract_session_token,
)
from chat_api.modules.auth.presentation.dtos import (
    AuthResponse,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    SwitchWorkspaceRequest,
    SwitchWorkspaceResponse,
    UserMeResponse,
    UserResponse,
    WorkspaceInfo,
)
from chat_api.shared.bus import CommandBusDep
from chat_api.config import settings

router = APIRouter(prefix="/auth", tags=["Authentication"])

COOKIE_NAME = "session_token"
COOKIE_MAX_AGE_SECONDS = 7 * 24 * 3600  # 7 days


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
def register(
    req: RegisterRequest,
    bus: CommandBusDep,
) -> UserResponse:
    user = bus.execute(
        RegisterCommand(
            email=req.email,
            password=req.password,
            full_name=req.full_name,
        )
    )
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Log in and create a new session",
)
def login(
    req: LoginRequest,
    request: Request,
    response: Response,
    bus: CommandBusDep,
) -> AuthResponse:
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")

    result = bus.execute(
        LoginCommand(
            email=req.email,
            password=req.password,
            ip_address=client_ip,
            user_agent=user_agent,
        )
    )

    # Set secure HTTP-only cookie
    response.set_cookie(
        key=COOKIE_NAME,
        value=result.session.token,
        max_age=COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite="lax",
        path="/",
    )

    return AuthResponse(
        user=UserResponse(
            id=result.user.id,
            email=result.user.email,
            full_name=result.user.full_name,
            is_active=result.user.is_active,
            created_at=result.user.created_at,
        ),
        active_workspace_id=result.session.active_workspace_id,
        session_token=result.session.token,
        expires_at=result.session.expires_at,
    )


@router.post(
    "/switch-workspace",
    response_model=SwitchWorkspaceResponse,
    summary="Switch active workspace context for the current session",
    dependencies=[Depends(RequireAuth())],
    openapi_extra=auth_openapi(),
)
def switch_workspace(
    req: SwitchWorkspaceRequest,
    auth: CurrentAuth,
) -> SwitchWorkspaceResponse:
    updated_session = auth.command_bus.execute(
        SwitchWorkspaceCommand(
            token=auth.session.token,
            workspace_id=req.workspace_id,
        )
    )
    return SwitchWorkspaceResponse(
        active_workspace_id=updated_session.active_workspace_id,  # type: ignore[arg-type]
        message="Active workspace switched successfully.",
    )


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Log out and invalidate session",
)
def logout(
    request: Request,
    response: Response,
    bus: CommandBusDep,
) -> MessageResponse:
    token = extract_session_token(request)
    if token:
        bus.execute(LogoutCommand(token=token))

    # Delete HTTP-only cookie
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return MessageResponse(message="Successfully logged out.")


@router.get(
    "/me",
    response_model=UserMeResponse,
    summary="Get profile of currently logged-in user with active workspace and workspace list",
    dependencies=[Depends(RequireAuth())],
    openapi_extra=auth_openapi(),
)
def get_me(
    auth: CurrentAuth,
) -> UserMeResponse:
    user = auth.user
    with auth.uow.read_only():
        workspaces = auth.uow.workspaces.list_by_user_id(user.id)
        workspace_infos: list[WorkspaceInfo] = []
        for w in workspaces:
            member_role = w.get_member_role(user.id)
            workspace_infos.append(
                WorkspaceInfo(
                    id=w.id,
                    name=w.name,
                    slug=w.slug,
                    role=member_role.value if member_role is not None else "member",
                    permissions=sorted(
                        auth.uow.workspaces.list_permissions(w.id, user.id)
                    ),
                )
            )

    return UserMeResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        created_at=user.created_at,
        active_workspace_id=auth.session.active_workspace_id,
        workspaces=workspace_infos,
    )
