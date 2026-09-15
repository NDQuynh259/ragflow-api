"""Authentication REST Router."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from chat_api.modules.auth.application.commands import (
    LoginCommand,
    LoginHandler,
    LogoutCommand,
    LogoutHandler,
    RegisterCommand,
    RegisterHandler,
    SwitchWorkspaceCommand,
    SwitchWorkspaceHandler,
)
from chat_api.modules.auth.domain.entity import UserSession
from chat_api.modules.auth.presentation.dependencies import (
    extract_session_token,
    get_current_session,
    get_current_user,
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
from chat_api.modules.users.domain.entity import User
from chat_api.shared.domain.uow import UnitOfWork
from chat_api.shared.infrastructure.database.uow import get_uow

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
    uow: UnitOfWork = Depends(get_uow),
) -> UserResponse:
    handler = RegisterHandler(uow)
    user = handler.handle(
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
    uow: UnitOfWork = Depends(get_uow),
) -> AuthResponse:
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")

    handler = LoginHandler(uow)
    result = handler.handle(
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
)
def switch_workspace(
    req: SwitchWorkspaceRequest,
    session: UserSession = Depends(get_current_session),
    uow: UnitOfWork = Depends(get_uow),
) -> SwitchWorkspaceResponse:
    handler = SwitchWorkspaceHandler(uow)
    updated_session = handler.handle(
        SwitchWorkspaceCommand(
            token=session.token,
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
    uow: UnitOfWork = Depends(get_uow),
) -> MessageResponse:
    token = extract_session_token(request)
    if token:
        handler = LogoutHandler(uow)
        handler.handle(LogoutCommand(token=token))

    # Delete HTTP-only cookie
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return MessageResponse(message="Successfully logged out.")


@router.get(
    "/me",
    response_model=UserMeResponse,
    summary="Get profile of currently logged-in user with active workspace and workspace list",
)
def get_me(
    session: UserSession = Depends(get_current_session),
    uow: UnitOfWork = Depends(get_uow),
) -> UserMeResponse:
    with uow:
        user = uow.users.get_by_id(session.user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found.",
            )
        workspaces = uow.workspaces.list_by_user_id(user.id)
        workspace_infos = [
            WorkspaceInfo(
                id=w.id,
                name=w.name,
                slug=w.slug,
                role=w.get_member_role(user.id).value if w.get_member_role(user.id) else "member",
            )
            for w in workspaces
        ]

    return UserMeResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        created_at=user.created_at,
        active_workspace_id=session.active_workspace_id,
        workspaces=workspace_infos,
    )
