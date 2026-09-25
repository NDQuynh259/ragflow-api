"""Integration tests for Modular Presentation layer (Routes & DTOs)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from chat_api.main import app
from chat_api.modules.auth.domain.entity import UserSession
from chat_api.modules.documents.presentation.router import get_queue, get_storage
from chat_api.modules.messages.presentation.router import get_rag_engine
from chat_api.modules.users.domain.entity import User
from chat_api.modules.workspaces.domain.entity import Workspace, WorkspaceMember, WorkspaceRole
from chat_api.shared.auth import AuthContext, get_auth_context
from chat_api.shared.infrastructure.database import get_uow
from core.cqrs import CommandBus, QueryBus
from core.security import CurrentPrincipal, ExecutionContext

TEST_USER = User(email="api-user@test.com")
TEST_SESSION_ID = uuid.uuid4()


def workspace_for_current_user(workspace_id: uuid.UUID, name: str, slug: str) -> Workspace:
    return Workspace(
        id=workspace_id,
        name=name,
        slug=slug,
        members=[
            WorkspaceMember(
                workspace_id=workspace_id,
                user_id=TEST_USER.id,
                role=WorkspaceRole.OWNER,
            )
        ],
    )


@pytest.fixture
def client(fake_uow, fake_storage, fake_queue, fake_rag):
    app.dependency_overrides[get_uow] = lambda: fake_uow
    app.dependency_overrides[get_storage] = lambda: fake_storage
    app.dependency_overrides[get_queue] = lambda: fake_queue
    app.dependency_overrides[get_rag_engine] = lambda: fake_rag
    principal = CurrentPrincipal(
        user_id=TEST_USER.id,
        session_id=TEST_SESSION_ID,
    )
    execution = ExecutionContext(principal=principal)
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        user=TEST_USER,
        session=UserSession(
            id=TEST_SESSION_ID,
            user_id=TEST_USER.id,
            token="test-session-token",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        ),
        principal=principal,
        command_bus=CommandBus(fake_uow, execution_context=execution),
        query_bus=QueryBus(fake_uow, execution_context=execution),
        uow=fake_uow,
    )

    with TestClient(app) as test_client:
        yield test_client, fake_uow

    app.dependency_overrides.clear()


def test_health_check(client):
    tc, _ = client
    response = tc.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "components" in data
    assert "database" in data["components"]
    assert "message_broker" in data["components"]
    assert "storage" in data["components"]
    assert "ai_providers" in data["components"]
    assert "scheduler" in data["components"]

    # Verify alias /api/v1/healthy
    res_healthy = tc.get("/api/v1/healthy")
    assert res_healthy.status_code == 200
    assert res_healthy.json()["status"] == "ok"

    # Verify un-prefixed /health is removed
    assert tc.get("/health").status_code == 404


def test_openapi_declares_route_permissions(client):
    tc, _ = client
    schema = tc.get("/openapi.json").json()

    create_session = schema["paths"]["/chat-sessions"]["post"]
    assert create_session["x-required-permissions"] == ["sessions:create"]

    attach_document = schema["paths"]["/chat-sessions/{session_id}/documents/attach"]["post"]
    assert attach_document["x-permission-mode"] == "all"
    assert attach_document["x-required-permissions"] == [
        "sessions:update",
        "documents:read",
    ]

    current_user = schema["paths"]["/auth/me"]["get"]
    assert current_user["x-authentication-required"] is True
    assert current_user["x-required-permissions"] == []


def test_create_and_get_session_api(client):
    tc, uow = client
    ws_id = uuid.uuid4()
    uow.workspaces.save(workspace_for_current_user(ws_id, "Workspace 1", "ws-1"))

    # 1. Create session
    payload = {
        "workspace_id": str(ws_id),
        "title": "Chính sách nghỉ phép",
        "rag_config": {"top_k": 3, "rerank": True},
    }
    create_res = tc.post("/chat-sessions", json=payload)
    assert create_res.status_code == 201
    created_data = create_res.json()
    assert created_data["title"] == "Chính sách nghỉ phép"
    session_id = created_data["id"]

    # 2. Get session
    get_res = tc.get(f"/chat-sessions/{session_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == session_id


def test_send_message_api(client):
    tc, uow = client
    ws_id = uuid.uuid4()
    uow.workspaces.save(workspace_for_current_user(ws_id, "Workspace 1", "ws-1"))

    create_res = tc.post("/chat-sessions", json={"workspace_id": str(ws_id), "title": "Test"})
    session_id = create_res.json()["id"]

    # Send message
    msg_res = tc.post(
        f"/chat-sessions/{session_id}/messages",
        json={"content": "Làm thế nào để xin nghỉ phép?"},
    )
    assert msg_res.status_code == 200
    data = msg_res.json()
    assert data["role"] == "assistant"
    assert data["content"] == "Câu trả lời RAG test"

    # List messages
    list_res = tc.get(f"/chat-sessions/{session_id}/messages")
    assert list_res.status_code == 200
    messages = list_res.json()
    assert len(messages) >= 1


def test_workspace_routes_reject_non_member(client):
    tc, uow = client
    workspace_id = uuid.uuid4()
    uow.workspaces.save(Workspace(id=workspace_id, name="Private", slug="private"))

    response = tc.post(
        "/chat-sessions",
        json={"workspace_id": str(workspace_id), "title": "Unauthorized"},
    )

    assert response.status_code == 403


def test_route_guard_denies_member_lacking_permission(client):
    """Member role lacks DOCUMENT_DELETE permission; Route Guard returns 403 Forbidden."""
    tc, uow = client
    ws_id = uuid.uuid4()
    uow.workspaces.save(
        Workspace(
            id=ws_id,
            name="Member WS",
            slug="member-ws",
            members=[
                WorkspaceMember(
                    workspace_id=ws_id,
                    user_id=TEST_USER.id,
                    role=WorkspaceRole.MEMBER,
                )
            ],
        )
    )

    from chat_api.modules.documents.domain.entity import Document, DocumentStatus

    doc_id = uuid.uuid4()
    uow.documents.save(
        Document(
            id=doc_id,
            workspace_id=ws_id,
            filename="secret.pdf",
            storage_uri="s3://bucket/secret.pdf",
            mime_type="application/pdf",
            file_size=200,
            content_hash="hash123",
            status=DocumentStatus.READY,
        )
    )

    response = tc.delete(f"/documents/{doc_id}")
    assert response.status_code == 403
    assert "documents:delete" in response.json()["error"]


def test_documents_api_uses_active_workspace(client):
    """GET /documents and POST /documents work directly without requiring /workspaces/{id} in path."""
    tc, uow = client
    ws_id = uuid.uuid4()
    uow.workspaces.save(workspace_for_current_user(ws_id, "Active WS", "active-ws"))

    from chat_api.modules.documents.domain.entity import Document, DocumentStatus

    doc_id = uuid.uuid4()
    uow.documents.save(
        Document(
            id=doc_id,
            workspace_id=ws_id,
            filename="handbook.pdf",
            storage_uri="s3://bucket/handbook.pdf",
            mime_type="application/pdf",
            file_size=500,
            content_hash="h1",
            status=DocumentStatus.READY,
        )
    )

    # 1. GET /documents with workspace_id
    resp = tc.get(f"/documents?workspace_id={ws_id}")
    assert resp.status_code == 200
    docs = resp.json()
    assert len(docs) == 1
    assert docs[0]["filename"] == "handbook.pdf"

    # 2. POST /documents upload
    upload_resp = tc.post(
        f"/documents?workspace_id={ws_id}",
        files={"file": ("guide.pdf", b"dummy pdf content", "application/pdf")},
    )
    assert upload_resp.status_code == 201
    assert upload_resp.json()["document"]["filename"] == "guide.pdf"
