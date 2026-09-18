"""Unit tests for ViShop-inspired authorization system.

Validates:
- Owner bypass mechanism (read-time full access wildcard)
- Built-in role permission calculation
- Dynamic effective permissions merging
- AND guards (require_permission) vs OR guards (require_any_permission)
- CurrentPrincipal helper methods
- FastAPI guard callables (RequirePermission, RequireAnyPermission, RequireRole)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from chat_api.modules.auth.domain.entity import UserSession
from chat_api.modules.users.domain.entity import User
from chat_api.shared.auth import (
    ALL_PERMISSION_CODES,
    BUILTIN_ROLE_PERMISSIONS,
    AuthContext,
    CurrentPrincipal,
    Permission,
    RequireAnyPermission,
    RequireAuth,
    RequirePermission,
    RequireRole,
    effective_permissions,
    require_auth,
)
from chat_api.shared.bus import CommandBus, QueryBus
from core.exceptions import ForbiddenException, UnauthenticatedException


def test_effective_permissions_owner_bypass():
    """Owner role must bypass all checks and return full catalog plus wildcard '*'."""
    perms = effective_permissions("owner")
    assert "*" in perms
    assert perms.issuperset(ALL_PERMISSION_CODES)
    # Even if stored_permissions in DB is empty, owner has all permissions
    perms_empty_db = effective_permissions("owner", stored_permissions=set())
    assert "*" in perms_empty_db
    assert perms_empty_db.issuperset(ALL_PERMISSION_CODES)


def test_effective_permissions_builtin_merging():
    """Built-in roles compute at read-time and merge with any custom stored permissions."""
    member_perms = effective_permissions("member")
    assert member_perms == BUILTIN_ROLE_PERMISSIONS["member"]
    assert Permission.DOCUMENT_READ.value in member_perms
    assert Permission.WORKSPACE_DELETE.value not in member_perms

    # Merging custom permission (set, Sequence, or tuple)
    custom_stored = {"custom:analytics", Permission.DOCUMENT_DELETE.value}
    merged = effective_permissions("member", stored_permissions=custom_stored)
    assert Permission.DOCUMENT_READ.value in merged
    assert Permission.DOCUMENT_DELETE.value in merged
    assert "custom:analytics" in merged
    assert Permission.WORKSPACE_DELETE.value not in merged

    # Verify Sequence/list input works identically
    sequence_stored = ["custom:analytics", Permission.DOCUMENT_DELETE.value]
    merged_seq = effective_permissions("member", stored_permissions=sequence_stored)
    assert merged_seq == merged


def test_effective_permissions_unknown_or_none():
    assert effective_permissions(None) == frozenset()
    assert effective_permissions("non_existent_role") == frozenset()


def test_principal_owner_bypass():
    """CurrentPrincipal with role='owner' passes all permission checks."""
    principal = CurrentPrincipal(
        user_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        role="owner",
        permissions=frozenset(),  # Even with empty permissions set!
    )
    assert principal.is_owner
    assert principal.has_permission(Permission.WORKSPACE_DELETE)
    assert principal.has_permission("any:arbitrary:key")
    assert principal.has_any_permission(Permission.WORKSPACE_DELETE, "other:key")
    assert principal.has_all_permissions(Permission.WORKSPACE_DELETE, Permission.WORKSPACE_READ)

    # Require methods do not raise
    principal.require_permission(Permission.WORKSPACE_DELETE)
    principal.require_any_permission("non_existent")


def test_principal_and_guard_logic():
    """require_permission implements strict AND logic (all must be present)."""
    principal = CurrentPrincipal(
        user_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        role="member",
        permissions=frozenset({Permission.SESSION_READ.value, Permission.MESSAGE_SEND.value}),
    )

    # Holding all -> passes
    principal.require_permission(Permission.SESSION_READ, Permission.MESSAGE_SEND)

    # Missing one -> raises ForbiddenException
    with pytest.raises(ForbiddenException) as exc_info:
        principal.require_permission(
            Permission.SESSION_READ,
            Permission.DOCUMENT_DELETE,
        )
    assert "Missing required permission" in str(exc_info.value)
    assert "documents:delete" in str(exc_info.value)


def test_principal_or_guard_logic():
    """require_any_permission implements OR logic (at least one must be present)."""
    principal = CurrentPrincipal(
        user_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        role="member",
        permissions=frozenset({Permission.SESSION_READ.value}),
    )

    # Holds at least one -> passes
    principal.require_any_permission(
        Permission.DOCUMENT_DELETE,  # Not held
        Permission.SESSION_READ,  # Held
    )

    # Holds none -> raises ForbiddenException
    with pytest.raises(ForbiddenException) as exc_info:
        principal.require_any_permission(
            Permission.DOCUMENT_DELETE,
            Permission.WORKSPACE_DELETE,
        )
    assert "Requires at least one of" in str(exc_info.value)


@pytest.mark.anyio
async def test_fastapi_dependency_guards():
    """Test RequirePermission, RequireAnyPermission, RequireRole as FastAPI callables."""
    user = User(id=uuid.uuid4(), email="test@example.com", full_name="Tester", is_active=True)
    session = UserSession(
        id=uuid.uuid4(),
        user_id=user.id,
        token="fake_tok",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )

    member_principal = CurrentPrincipal(
        user_id=user.id,
        session_id=session.id,
        role="member",
        permissions=frozenset({Permission.DOCUMENT_READ.value}),
    )
    auth_ctx = AuthContext(
        user=user,
        session=session,
        principal=member_principal,
        command_bus=CommandBus(None),
        query_bus=QueryBus(None),
        uow=None,
    )

    # RequirePermission (AND)
    and_guard = RequirePermission(Permission.DOCUMENT_READ)
    res = await and_guard(auth_ctx)
    assert res == auth_ctx

    and_fail_guard = RequirePermission(Permission.DOCUMENT_READ, Permission.DOCUMENT_DELETE)
    with pytest.raises(ForbiddenException):
        await and_fail_guard(auth_ctx)

    # RequireAnyPermission (OR)
    or_guard = RequireAnyPermission(Permission.DOCUMENT_DELETE, Permission.DOCUMENT_READ)
    assert await or_guard(auth_ctx) == auth_ctx

    or_fail_guard = RequireAnyPermission(Permission.DOCUMENT_DELETE, Permission.WORKSPACE_DELETE)
    with pytest.raises(ForbiddenException):
        await or_fail_guard(auth_ctx)

    # RequireRole
    role_guard = RequireRole("member", "admin")
    assert await role_guard(auth_ctx) == auth_ctx

    role_fail_guard = RequireRole("owner", "superadmin")
    with pytest.raises(ForbiddenException):
        await role_fail_guard(auth_ctx)

    # RequireAuth
    auth_guard = RequireAuth()
    assert await auth_guard(auth_ctx) == auth_ctx
    assert await require_auth(auth_ctx) == auth_ctx

    with pytest.raises(UnauthenticatedException):
        await auth_guard(None)

    with pytest.raises(UnauthenticatedException):
        await require_auth(None)


def test_sqlalchemy_workspace_repository_effective_permissions():
    """Verify SqlAlchemyWorkspaceRepository uses effective_permissions calculation."""
    from unittest.mock import MagicMock

    from chat_api.modules.workspaces.infrastructure.repository import SqlAlchemyWorkspaceRepository

    mock_session = MagicMock()
    repo = SqlAlchemyWorkspaceRepository(mock_session)

    ws_id = uuid.uuid4()
    user_id = uuid.uuid4()

    # Case 1: Role is Owner -> bypass and returns wildcard and all permissions
    mock_session.scalar.return_value = "owner"
    mock_session.scalars.return_value.all.return_value = []

    owner_perms = repo.list_permissions(ws_id, user_id)
    assert "*" in owner_perms
    assert Permission.WORKSPACE_DELETE.value in owner_perms
    assert repo.has_permission(ws_id, user_id, Permission.WORKSPACE_DELETE.value)

    # Case 2: Role is Member with custom permission
    mock_session.scalar.return_value = "member"
    mock_session.scalars.return_value.all.return_value = ["custom:export"]

    member_perms = repo.list_permissions(ws_id, user_id)
    assert Permission.DOCUMENT_READ.value in member_perms
    assert "custom:export" in member_perms
    assert Permission.WORKSPACE_DELETE.value not in member_perms
    assert repo.has_permission(ws_id, user_id, "custom:export")
    assert not repo.has_permission(ws_id, user_id, Permission.WORKSPACE_DELETE.value)

    # Case 3: User is not a member
    mock_session.scalar.return_value = None
    no_perms = repo.list_permissions(ws_id, user_id)
    assert len(no_perms) == 0
    assert not repo.has_permission(ws_id, user_id, Permission.DOCUMENT_READ.value)
