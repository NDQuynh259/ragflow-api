"""Unit tests for WorkspaceResolutionService."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from chat_api.shared.auth.guards import AuthContext
from chat_api.shared.auth.workspace_resolver import WorkspaceResolutionService


@pytest.mark.anyio
async def test_resolve_from_path_param() -> None:
    expected_ws_id = uuid.uuid4()
    request = MagicMock()
    request.path_params = {"workspace_id": str(expected_ws_id)}
    auth = MagicMock(spec=AuthContext)

    resolved = await WorkspaceResolutionService.resolve_workspace_id(request, auth)
    assert resolved == expected_ws_id


@pytest.mark.anyio
async def test_resolve_from_header() -> None:
    expected_ws_id = uuid.uuid4()
    request = MagicMock()
    request.path_params = {}
    request.headers = {"X-Workspace-Id": str(expected_ws_id)}
    auth = MagicMock(spec=AuthContext)

    resolved = await WorkspaceResolutionService.resolve_workspace_id(request, auth)
    assert resolved == expected_ws_id


@pytest.mark.anyio
async def test_resolve_from_query_param() -> None:
    expected_ws_id = uuid.uuid4()
    request = MagicMock()
    request.path_params = {}
    request.headers = {}
    request.query_params = {"workspace_id": str(expected_ws_id)}
    auth = MagicMock(spec=AuthContext)

    resolved = await WorkspaceResolutionService.resolve_workspace_id(request, auth)
    assert resolved == expected_ws_id


@pytest.mark.anyio
async def test_resolve_from_body_json() -> None:
    expected_ws_id = uuid.uuid4()
    request = MagicMock()
    request.path_params = {}
    request.headers = {}
    request.query_params = {}
    request.method = "POST"
    request.body = AsyncMock(return_value=f'{{"workspace_id": "{expected_ws_id}"}}'.encode())
    auth = MagicMock(spec=AuthContext)

    resolved = await WorkspaceResolutionService.resolve_workspace_id(request, auth)
    assert resolved == expected_ws_id


@pytest.mark.anyio
async def test_resolve_fallback_to_session() -> None:
    expected_ws_id = uuid.uuid4()
    request = MagicMock()
    request.path_params = {}
    request.headers = {}
    request.query_params = {}
    request.method = "GET"
    auth = MagicMock(spec=AuthContext)
    auth.principal.active_workspace_id = expected_ws_id

    resolved = await WorkspaceResolutionService.resolve_workspace_id(request, auth)
    assert resolved == expected_ws_id
