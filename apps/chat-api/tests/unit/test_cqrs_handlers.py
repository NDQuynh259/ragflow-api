"""Unit tests for CQRS Handlers across modules."""

import uuid

import pytest

from chat_api.modules.chat_sessions.application.commands import (
    AttachDocumentCommand,
    AttachDocumentHandler,
    CreateSessionCommand,
    CreateSessionHandler,
)
from chat_api.modules.chat_sessions.application.queries import (
    GetSessionHandler,
    GetSessionQuery,
)
from chat_api.modules.documents.application.commands import (
    UploadDocumentCommand,
)
from chat_api.modules.documents.domain.entity import Document, DocumentStatus
from chat_api.modules.messages.application.commands import (
    SendMessageCommand,
    SendMessageHandler,
)
from chat_api.modules.users.domain.entity import User
from chat_api.modules.workspaces.domain.entity import Workspace, WorkspaceMember, WorkspaceRole
from chat_api.shared.bus import CommandBus
from core.auth import CurrentPrincipal, ExecutionContext
from core.exceptions import ForbiddenException
from core.queue import IngestionQueuePort
from core.storage import ObjectStoragePort


def test_create_and_get_session(fake_uow):
    ws_id = uuid.uuid4()
    fake_uow.workspaces.save(Workspace(id=ws_id, name="Test WS", slug="test-ws"))

    handler = CreateSessionHandler(fake_uow)
    session_dto = handler.handle(CreateSessionCommand(workspace_id=ws_id, title="Test Session"))

    assert session_dto.title == "Test Session"
    assert session_dto.workspace_id == ws_id

    query_handler = GetSessionHandler(fake_uow)
    fetched = query_handler.handle(GetSessionQuery(session_id=session_dto.id))
    assert fetched.id == session_dto.id


def test_upload_document_and_attach(fake_uow, fake_storage, fake_queue):
    ws_id = uuid.uuid4()
    user = User(email="member@test.com")
    fake_uow.users.save(user)
    fake_uow.workspaces.save(
        Workspace(
            id=ws_id,
            name="Test WS",
            slug="test-ws",
            members=[
                WorkspaceMember(
                    workspace_id=ws_id,
                    user_id=user.id,
                    role=WorkspaceRole.ADMIN,
                )
            ],
        )
    )

    # Create session
    session_dto = CreateSessionHandler(fake_uow).handle(
        CreateSessionCommand(workspace_id=ws_id, title="Chat")
    )

    # Upload document
    command_bus = CommandBus(
        fake_uow,
        execution_context=ExecutionContext(
            principal=CurrentPrincipal(user_id=user.id, session_id=uuid.uuid4())
        ),
        dependencies={
            ObjectStoragePort: fake_storage,
            IngestionQueuePort: fake_queue,
        },
    )
    doc_dto = command_bus.execute(
        UploadDocumentCommand(
            workspace_id=ws_id,
            filename="sop.pdf",
            content=b"Sample PDF Content",
        )
    )

    assert doc_dto.filename == "sop.pdf"
    assert doc_dto.status == "queued"
    assert len(fake_queue.enqueued) == 1

    # Attach to session
    attach_handler = AttachDocumentHandler(fake_uow)
    updated_session = attach_handler.handle(
        AttachDocumentCommand(session_id=session_dto.id, document_id=doc_dto.id)
    )
    assert doc_dto.id in updated_session.attached_document_ids


def test_member_cannot_upload_document(fake_uow, fake_storage, fake_queue):
    workspace_id = uuid.uuid4()
    user = User(email="limited-member@test.com")
    fake_uow.users.save(user)
    fake_uow.workspaces.save(
        Workspace(
            id=workspace_id,
            name="Limited Workspace",
            slug="limited-workspace",
            members=[
                WorkspaceMember(
                    workspace_id=workspace_id,
                    user_id=user.id,
                    role=WorkspaceRole.MEMBER,
                )
            ],
        )
    )
    bus = CommandBus(
        fake_uow,
        execution_context=ExecutionContext(
            principal=CurrentPrincipal(user_id=user.id, session_id=uuid.uuid4())
        ),
        dependencies={
            ObjectStoragePort: fake_storage,
            IngestionQueuePort: fake_queue,
        },
    )

    with pytest.raises(ForbiddenException, match="documents:create"):
        bus.execute(
            UploadDocumentCommand(
                workspace_id=workspace_id,
                filename="restricted.pdf",
                content=b"restricted",
            )
        )

    assert fake_queue.enqueued == []


def test_send_message_flow(fake_uow, fake_rag):
    ws_id = uuid.uuid4()
    fake_uow.workspaces.save(Workspace(id=ws_id, name="Test WS", slug="test-ws"))

    session = CreateSessionHandler(fake_uow).handle(CreateSessionCommand(workspace_id=ws_id))

    # Mark a document as ready
    doc = Document(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        filename="manual.pdf",
        storage_uri="fake://uri",
        content_hash="hash123",
        status=DocumentStatus.READY,
    )
    fake_uow.documents.save(doc)
    AttachDocumentHandler(fake_uow).handle(
        AttachDocumentCommand(session_id=session.id, document_id=doc.id)
    )

    # Send message
    msg_handler = SendMessageHandler(fake_uow, fake_rag)
    msg_dto = msg_handler.handle(
        SendMessageCommand(session_id=session.id, content="Quy trình là gì?")
    )

    assert msg_dto.role == "assistant"
    assert msg_dto.content == "Câu trả lời RAG test"
    assert len(msg_dto.citations) == 1
    assert msg_dto.citations[0].chunk_id == "chunk_1"


def test_principal_permissions_and_roles():
    from chat_api.shared.auth import (
        CurrentPrincipal,
        Permission,
        get_permissions_for_role,
    )
    from core.exceptions import ForbiddenException

    # 1. Owner has wildcard access to all permissions
    owner_principal = CurrentPrincipal(
        user_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        role="owner",
        permissions=get_permissions_for_role("owner"),
    )
    assert owner_principal.has_permission(Permission.WORKSPACE_DELETE)
    assert owner_principal.has_permission(Permission.DOCUMENT_CREATE)
    assert owner_principal.has_role("owner")
    owner_principal.require_permission(Permission.WORKSPACE_DELETE)  # should not raise
    owner_principal.require_role("owner", "admin")  # should not raise

    # 2. Member has limited permissions
    member_principal = CurrentPrincipal(
        user_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        role="member",
        permissions=get_permissions_for_role("member"),
    )
    assert member_principal.has_permission(Permission.DOCUMENT_READ)
    assert member_principal.has_permission(Permission.SESSION_UPDATE)
    assert not member_principal.has_permission(Permission.DOCUMENT_DELETE)
    assert member_principal.has_role("member")

    with pytest.raises(ForbiddenException, match="Missing required permission"):
        member_principal.require_permission(Permission.DOCUMENT_DELETE)

    with pytest.raises(ForbiddenException, match="User requires one of roles"):
        member_principal.require_role("admin", "owner")


def test_workspace_models_submodule_imports():
    from chat_api.modules.workspaces.infrastructure.models import (
        Permission,
        Role,
        RolePermission,
        Workspace,
        WorkspaceMember,
    )
    from chat_api.modules.workspaces.infrastructure.models.permission import Permission as PermMod
    from chat_api.modules.workspaces.infrastructure.models.role import Role as RoleMod
    from chat_api.modules.workspaces.infrastructure.models.role_permission import (
        RolePermission as RolePermMod,
    )
    from chat_api.modules.workspaces.infrastructure.models.workspace import Workspace as WsMod
    from chat_api.modules.workspaces.infrastructure.models.workspace_member import (
        WorkspaceMember as WsMemMod,
    )

    assert Permission is PermMod
    assert Role is RoleMod
    assert RolePermission is RolePermMod
    assert Workspace is WsMod
    assert WorkspaceMember is WsMemMod
