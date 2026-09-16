"""API integration tests for Permission Catalog endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid
import pytest
from fastapi.testclient import TestClient

from chat_api.main import app
from chat_api.modules.auth.domain.entity import UserSession
from chat_api.modules.auth.presentation.dependencies import AuthContext, get_auth_context
from chat_api.modules.users.domain.entity import User
from chat_api.shared.application.authorization import (
    PERMISSION_CATALOG,
    CurrentPrincipal,
    ExecutionContext,
)
from chat_api.shared.application.bus import CommandBus, QueryBus
from chat_api.shared.infrastructure.database.uow import get_uow


@pytest.fixture
def auth_client(fake_uow):
    user = User(id=uuid.uuid4(), email="member@example.com", full_name="Workspace Member")
    session = UserSession(
        id=uuid.uuid4(),
        user_id=user.id,
        token="valid-token",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    principal = CurrentPrincipal(
        user_id=user.id,
        session_id=session.id,
        role="member",
    )
    execution = ExecutionContext(principal=principal)

    app.dependency_overrides[get_uow] = lambda: fake_uow
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        user=user,
        session=session,
        principal=principal,
        command_bus=CommandBus(fake_uow, execution_context=execution),
        query_bus=QueryBus(fake_uow, execution_context=execution),
        uow=fake_uow,
    )
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_permission_catalog_requires_authentication():
    """Unauthenticated call to permission catalog returns 401."""
    app.dependency_overrides.clear()
    client = TestClient(app)
    resp = client.get("/api/v1/workspaces/permissions/catalog")
    assert resp.status_code == 401


def test_get_permission_catalog_workspaces_endpoint(auth_client):
    """Authenticated call returns structured permission catalog grouped by module."""
    resp = auth_client.get("/api/v1/workspaces/permissions/catalog")
    assert resp.status_code == 200

    data = resp.json()
    assert "groups" in data
    assert "total" in data
    assert data["total"] == len(PERMISSION_CATALOG)

    modules = {group["module"] for group in data["groups"]}
    assert {"workspace", "documents", "sessions", "messages"}.issubset(modules)

    for group in data["groups"]:
        assert len(group["permissions"]) > 0
        for perm in group["permissions"]:
            assert "code" in perm
            assert "name" in perm
            assert "description" in perm
            assert perm["module"] == group["module"]


def test_get_permission_catalog_root_alias_endpoint(auth_client):
    """Catalog is also accessible directly via /api/v1/permissions/catalog."""
    resp = auth_client.get("/api/v1/permissions/catalog")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == len(PERMISSION_CATALOG)
