"""Unit tests for Workspace application services."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from chat_api.modules.users.domain.entity import User
from chat_api.modules.workspaces.application import WorkspaceProvisioningService
from chat_api.modules.workspaces.domain.entity import WorkspaceRole


def test_create_default_workspace_with_fullname() -> None:
    uow = MagicMock()
    user = User(
        id=uuid.uuid4(),
        email="john.doe@example.com",
        full_name="John Doe",
        hashed_password="hash",
    )

    service = WorkspaceProvisioningService(uow)
    workspace = service.create_default_workspace(user)

    assert workspace.name == "John Doe's Workspace"
    assert workspace.slug == f"workspace-{user.id.hex[:8]}"
    assert len(workspace.members) == 1
    assert workspace.members[0].user_id == user.id
    assert workspace.members[0].role == WorkspaceRole.OWNER
    uow.workspaces.save.assert_called_once_with(workspace)


def test_create_default_workspace_without_fullname_uses_email_prefix() -> None:
    uow = MagicMock()
    user = User(
        id=uuid.uuid4(),
        email="alice@company.org",
        full_name=None,
        hashed_password="hash",
    )

    service = WorkspaceProvisioningService(uow)
    workspace = service.create_default_workspace(user)

    assert workspace.name == "alice's Workspace"
    assert workspace.slug == f"workspace-{user.id.hex[:8]}"
    assert workspace.members[0].role == WorkspaceRole.OWNER
    uow.workspaces.save.assert_called_once_with(workspace)
