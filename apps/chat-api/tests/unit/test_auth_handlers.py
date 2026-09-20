"""Unit tests for Auth CQRS Handlers."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from chat_api.modules.auth.application.commands import (
    LoginCommand,
    LoginHandler,
    LogoutCommand,
    LogoutHandler,
    RegisterCommand,
    RegisterHandler,
)
from chat_api.modules.auth.application.queries import (
    GetAuthenticationContextHandler,
    GetAuthenticationContextQuery,
    GetCurrentUserHandler,
    GetCurrentUserQuery,
)
from chat_api.modules.auth.domain.entity import UserSession
from chat_api.modules.auth.infrastructure.repository import SqlAlchemyUserSessionRepository
from chat_api.shared.auth import Permission
from core.security import hash_session_token, verify_password
from core.exceptions import (
    DomainValidationException,
    ForbiddenException,
    ResourceConflictException,
    UnauthenticatedException,
)


def test_register_success(fake_uow):
    handler = RegisterHandler(fake_uow)
    user = handler.handle(
        RegisterCommand(
            email="TestUser@Example.com",
            password="secretpassword123",
            full_name="Test User",
        )
    )

    assert user.email == "testuser@example.com"
    assert user.full_name == "Test User"
    assert verify_password("secretpassword123", user.hashed_password)
    assert fake_uow.committed is False


def test_session_token_hash_is_stable_and_not_plaintext():
    token = "a-sensitive-session-token"

    assert hash_session_token(token) == hash_session_token(token)
    assert hash_session_token(token) != token
    assert len(hash_session_token(token)) == 64


def test_session_repository_only_persists_token_hash():
    database_session = MagicMock()
    database_session.query.return_value.filter.return_value.first.return_value = None
    repository = SqlAlchemyUserSessionRepository(database_session)
    raw_token = "raw-session-credential"
    session = UserSession(
        user_id=uuid.uuid4(),
        token=raw_token,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )

    repository.save(session)

    persisted = database_session.add.call_args.args[0]
    assert persisted.token_hash == hash_session_token(raw_token)
    assert persisted.token_hash != raw_token


def test_session_repository_hashes_token_before_lookup():
    database_session = MagicMock()
    database_session.query.return_value.filter.return_value.first.return_value = None
    repository = SqlAlchemyUserSessionRepository(database_session)
    raw_token = "raw-session-credential"

    assert repository.get_by_token(raw_token) is None

    predicate = database_session.query.return_value.filter.call_args.args[0]
    assert predicate.right.value == hash_session_token(raw_token)


def test_register_duplicate_email_fails(fake_uow):
    handler = RegisterHandler(fake_uow)
    handler.handle(RegisterCommand(email="user@test.com", password="password123"))

    with pytest.raises(ResourceConflictException):
        handler.handle(RegisterCommand(email="USER@test.com", password="otherpassword"))


def test_register_invalid_inputs(fake_uow):
    handler = RegisterHandler(fake_uow)

    with pytest.raises(DomainValidationException):
        handler.handle(RegisterCommand(email="notanemail", password="password123"))

    with pytest.raises(DomainValidationException):
        handler.handle(RegisterCommand(email="valid@test.com", password="123"))


def test_login_and_get_current_user_flow(fake_uow):
    # 1. Register
    reg_handler = RegisterHandler(fake_uow)
    user = reg_handler.handle(RegisterCommand(email="alice@test.com", password="password123"))

    # 2. Login
    login_handler = LoginHandler(fake_uow)
    login_result = login_handler.handle(
        LoginCommand(
            email="alice@test.com",
            password="password123",
            ip_address="127.0.0.1",
            user_agent="pytest",
        )
    )

    assert login_result.user.id == user.id
    token = login_result.session.token
    assert len(token) > 20

    # 3. Get Current User via Session Token
    query_handler = GetCurrentUserHandler(fake_uow)
    fetched_user = query_handler.handle(GetCurrentUserQuery(token=token))
    assert fetched_user.id == user.id
    assert fetched_user.email == "alice@test.com"

    authentication = GetAuthenticationContextHandler(fake_uow).handle(
        GetAuthenticationContextQuery(token=token)
    )
    assert authentication.session.id == login_result.session.id
    assert authentication.user.id == user.id
    assert authentication.principal.role == "owner"
    assert authentication.principal.has_permission(Permission.DOCUMENT_CREATE)


def test_login_wrong_password_fails(fake_uow):
    RegisterHandler(fake_uow).handle(
        RegisterCommand(email="bob@test.com", password="correctpassword")
    )

    with pytest.raises(UnauthenticatedException):
        LoginHandler(fake_uow).handle(LoginCommand(email="bob@test.com", password="wrongpassword"))


def test_logout_invalidates_session(fake_uow):
    RegisterHandler(fake_uow).handle(
        RegisterCommand(email="charlie@test.com", password="password123")
    )
    login_result = LoginHandler(fake_uow).handle(
        LoginCommand(email="charlie@test.com", password="password123")
    )
    token = login_result.session.token

    # Logout
    logout_success = LogoutHandler(fake_uow).handle(LogoutCommand(token=token))
    assert logout_success is True

    # Subsequent check fails
    query_handler = GetCurrentUserHandler(fake_uow)
    with pytest.raises(UnauthenticatedException):
        query_handler.handle(GetCurrentUserQuery(token=token))


def test_expired_session_fails(fake_uow):
    reg = RegisterHandler(fake_uow).handle(
        RegisterCommand(email="david@test.com", password="password123")
    )
    # Insert expired session
    expired_session = UserSession(
        user_id=reg.id,
        token="expired_token_123",
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )
    fake_uow.user_sessions.save(expired_session)

    with pytest.raises(UnauthenticatedException):
        GetCurrentUserHandler(fake_uow).handle(GetCurrentUserQuery(token="expired_token_123"))


def test_register_creates_default_workspace_and_login_sets_active(fake_uow):
    from chat_api.modules.auth.application.commands import (
        SwitchWorkspaceCommand,
        SwitchWorkspaceHandler,
    )
    from chat_api.modules.workspaces.domain.entity import (
        Workspace,
        WorkspaceMember,
        WorkspaceRole,
    )

    # 1. Register user
    user = RegisterHandler(fake_uow).handle(
        RegisterCommand(
            email="developer@company.com",
            password="securePassword123",
            full_name="Lead Developer",
        )
    )

    # Verify default workspace was automatically created
    user_workspaces = fake_uow.workspaces.list_by_user_id(user.id)
    assert len(user_workspaces) == 1
    default_ws = user_workspaces[0]
    assert "Lead Developer" in default_ws.name
    assert default_ws.is_member(user.id) is True
    assert default_ws.get_member_role(user.id) == WorkspaceRole.OWNER

    # 2. Login sets active_workspace_id
    login_result = LoginHandler(fake_uow).handle(
        LoginCommand(email="developer@company.com", password="securePassword123")
    )
    assert login_result.session.active_workspace_id == default_ws.id

    # 3. Create a second workspace and add user as member
    second_ws = Workspace(
        name="Team Workspace",
        slug="team-workspace",
        members=[
            WorkspaceMember(
                workspace_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
                user_id=user.id,
                role=WorkspaceRole.MEMBER,
            )
        ],
    )
    second_ws.members[0].workspace_id = second_ws.id
    fake_uow.workspaces.save(second_ws)

    # User now belongs to 2 workspaces
    assert len(fake_uow.workspaces.list_by_user_id(user.id)) == 2

    # 4. Switch workspace
    switch_handler = SwitchWorkspaceHandler(fake_uow)
    updated_session = switch_handler.handle(
        SwitchWorkspaceCommand(
            token=login_result.session.token,
            workspace_id=second_ws.id,
        )
    )
    assert updated_session.active_workspace_id == second_ws.id

    # 5. Switch to unauthorized workspace fails
    unauthorized_ws = Workspace(
        name="Private Workspace",
        slug="private-ws",
        members=[],  # User is not a member
    )
    fake_uow.workspaces.save(unauthorized_ws)

    with pytest.raises(ForbiddenException):
        switch_handler.handle(
            SwitchWorkspaceCommand(
                token=login_result.session.token,
                workspace_id=unauthorized_ws.id,
            )
        )


def test_auth_submodule_imports():
    from chat_api.modules.auth.application.commands.login_command import LoginCommand, LoginHandler
    from chat_api.modules.auth.application.commands.logout_command import (
        LogoutCommand,
        LogoutHandler,
    )
    from chat_api.modules.auth.application.commands.register_command import (
        RegisterCommand,
        RegisterHandler,
    )
    from chat_api.modules.auth.application.commands.switch_workspace_command import (
        SwitchWorkspaceCommand,
        SwitchWorkspaceHandler,
    )
    from chat_api.modules.auth.application.queries.get_current_user_query import (
        GetCurrentUserHandler,
        GetCurrentUserQuery,
    )

    assert LoginCommand and LoginHandler
    assert LogoutCommand and LogoutHandler
    assert RegisterCommand and RegisterHandler
    assert SwitchWorkspaceCommand and SwitchWorkspaceHandler
    assert GetCurrentUserQuery and GetCurrentUserHandler


def test_command_bus_and_query_bus_flow(fake_uow):
    from chat_api.modules.auth.application.commands import (
        LoginCommand,
        LogoutCommand,
        RegisterCommand,
    )
    from chat_api.modules.auth.application.queries import GetCurrentUserQuery
    from chat_api.shared.bus import Command, CommandBus, QueryBus

    cmd_bus = CommandBus(fake_uow)
    query_bus = QueryBus(fake_uow)

    # 1. Register via CommandBus
    user = cmd_bus.execute(
        RegisterCommand(
            email="bus_user@test.com",
            password="secretpassword123",
            full_name="Bus User",
        )
    )
    assert user.email == "bus_user@test.com"

    # 2. Login via CommandBus
    login_result = cmd_bus.execute(
        LoginCommand(
            email="bus_user@test.com",
            password="secretpassword123",
        )
    )
    assert login_result.user.id == user.id
    assert login_result.session.token is not None

    # 3. Get Current User via QueryBus
    current_user = query_bus.execute(GetCurrentUserQuery(token=login_result.session.token))
    assert current_user.id == user.id

    # 4. Logout via CommandBus
    logged_out = cmd_bus.execute(LogoutCommand(token=login_result.session.token))
    assert logged_out is True

    # 5. Unregistered command raises RuntimeError
    class UnknownCommand(Command[str]):
        pass

    with pytest.raises(RuntimeError, match="No handler registered"):
        cmd_bus.execute(UnknownCommand())
