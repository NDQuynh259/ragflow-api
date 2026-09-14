"""Unit tests for CQRS Handlers across modules."""

import uuid
from chat_api.modules.documents.application.commands import (
    UploadDocumentCommand,
    UploadDocumentHandler,
)
from chat_api.modules.documents.application.queries import (
    GetDocumentHandler,
    GetDocumentQuery,
)
from chat_api.modules.documents.domain.entity import Document, DocumentStatus
from chat_api.modules.messages.application.commands import (
    SendMessageCommand,
    SendMessageHandler,
)
from chat_api.modules.sessions.application.commands import (
    AttachDocumentCommand,
    AttachDocumentHandler,
    CreateSessionCommand,
    CreateSessionHandler,
)
from chat_api.modules.sessions.application.queries import (
    GetSessionHandler,
    GetSessionQuery,
)
from chat_api.modules.workspaces.domain.entity import Workspace


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
    fake_uow.workspaces.save(Workspace(id=ws_id, name="Test WS", slug="test-ws"))

    # Create session
    session_dto = CreateSessionHandler(fake_uow).handle(CreateSessionCommand(workspace_id=ws_id, title="Chat"))

    # Upload document
    upload_handler = UploadDocumentHandler(fake_uow, fake_storage, fake_queue)
    doc_dto = upload_handler.handle(
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
    AttachDocumentHandler(fake_uow).handle(AttachDocumentCommand(session_id=session.id, document_id=doc.id))

    # Send message
    msg_handler = SendMessageHandler(fake_uow, fake_rag)
    msg_dto = msg_handler.handle(SendMessageCommand(session_id=session.id, content="Quy trình là gì?"))

    assert msg_dto.role == "assistant"
    assert msg_dto.content == "Câu trả lời RAG test"
    assert len(msg_dto.citations) == 1
    assert msg_dto.citations[0].chunk_id == "chunk_1"
