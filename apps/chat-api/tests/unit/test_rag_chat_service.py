"""Unit tests for RAGChatOrchestratorService."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from chat_api.modules.chat_sessions.domain.entity import ChatSession
from chat_api.modules.messages.application.mapper import MessageMapper
from chat_api.modules.messages.application.services import RAGChatOrchestratorService
from chat_api.modules.messages.domain.entity import Message, MessageRole
from chat_api.modules.messages.presentation.dtos import CitationResponse


def test_rag_chat_orchestrator_preserves_citation_when_presigning_fails(caplog) -> None:
    uow = MagicMock()
    rag_engine = MagicMock()
    document_id = uuid.uuid4()
    uow.documents.get_ready_documents_by_ids.return_value = []
    rag_engine.answer.return_value = (
        "Answer",
        [
            {
                "document_id": str(document_id),
                "chunk_id": "image-chunk",
                "page_number": 1,
                "image_uri": "file:///tmp/evidence.png",
            }
        ],
        {},
    )
    storage = MagicMock()
    storage.presigned_get_url.side_effect = RuntimeError("storage unavailable")
    session = ChatSession(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        title="Test Session",
        rag_config={},
    )

    result = RAGChatOrchestratorService(uow, rag_engine, storage=storage).execute_chat(
        session, "Question"
    )

    assert len(result.assistant_message.citations) == 1
    assert result.assistant_message.citations[0].image_url is None
    assert "Failed to generate presigned image URL" in caplog.text


def test_message_add_citation_accepts_image_url() -> None:
    message = Message(
        id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        role=MessageRole.ASSISTANT,
        content="Answer",
    )

    citation = message.add_citation(
        chunk_id="image-chunk",
        document_id=uuid.uuid4(),
        page_number=1,
        image_url="https://signed.example/image.png",
    )

    assert citation.image_url == "https://signed.example/image.png"


def test_rag_chat_orchestrator_service_flow() -> None:
    uow = MagicMock()
    rag_engine = MagicMock()

    doc_id = uuid.uuid4()
    mock_doc = MagicMock(id=doc_id)
    uow.documents.get_ready_documents_by_ids.return_value = [mock_doc]

    session = ChatSession(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        title="Test Session",
        rag_config={"top_k": 3},
        attached_document_ids=[doc_id],
    )

    rag_engine.answer.return_value = (
        "This is the synthesized answer.",
        [
            {
                "chunk_id": "c1",
                "document_id": str(doc_id),
                "page_number": 2,
                "bbox": [0, 0, 10, 10],
                "quote": "Sample quote",
                "relevance_score": 0.95,
                "image_uri": "s3://images/evidence.png",
            }
        ],
        {"prompt_tokens": 120, "completion_tokens": 40},
    )

    storage = MagicMock()
    storage.presigned_get_url.return_value = "https://signed.example/evidence.png"
    service = RAGChatOrchestratorService(uow, rag_engine, storage=storage)
    result = service.execute_chat(session, "What is the policy?")

    # Verify user message
    assert result.user_message.role == MessageRole.USER
    assert result.user_message.content == "What is the policy?"

    # Verify assistant message & citations
    assert result.assistant_message.role == MessageRole.ASSISTANT
    assert result.assistant_message.content == "This is the synthesized answer."
    assert result.assistant_message.prompt_tokens == 120
    assert result.assistant_message.completion_tokens == 40
    assert len(result.assistant_message.citations) == 1
    assert result.assistant_message.citations[0].document_id == doc_id
    assert result.assistant_message.citations[0].page_number == 2
    assert result.assistant_message.citations[0].image_url == "https://signed.example/evidence.png"
    storage.presigned_get_url.assert_called_once_with(
        "s3://images/evidence.png",
        expires_in=3600,
    )

    citation_dto = MessageMapper.to_dto(result.assistant_message).citations[0]
    assert citation_dto.image_url == "https://signed.example/evidence.png"
    response = CitationResponse(**citation_dto.__dict__)
    assert response.image_url == "https://signed.example/evidence.png"

    # Verify uow tracking
    uow.track.assert_called_once_with(result.user_message, result.assistant_message)
    rag_engine.answer.assert_called_once_with(
        query="What is the policy?",
        document_ids=[str(doc_id)],
        top_k=3,
        workspace_id=str(session.workspace_id),
    )
