"""Integration tests for Modular Presentation layer (Routes & DTOs)."""

import uuid
import pytest
from fastapi.testclient import TestClient

from chat_api.main import app
from chat_api.modules.documents.presentation.router import get_queue, get_storage
from chat_api.modules.messages.presentation.router import get_rag_engine
from chat_api.modules.workspaces.domain.entity import Workspace
from chat_api.shared.infrastructure.database.uow import get_uow


@pytest.fixture
def client(fake_uow, fake_storage, fake_queue, fake_rag):
    app.dependency_overrides[get_uow] = lambda: fake_uow
    app.dependency_overrides[get_storage] = lambda: fake_storage
    app.dependency_overrides[get_queue] = lambda: fake_queue
    app.dependency_overrides[get_rag_engine] = lambda: fake_rag

    with TestClient(app) as test_client:
        yield test_client, fake_uow

    app.dependency_overrides.clear()


def test_health_check(client):
    tc, _ = client
    response = tc.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_create_and_get_session_api(client):
    tc, uow = client
    ws_id = uuid.uuid4()
    uow.workspaces.save(Workspace(id=ws_id, name="Workspace 1", slug="ws-1"))

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
    uow.workspaces.save(Workspace(id=ws_id, name="Workspace 1", slug="ws-1"))

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
