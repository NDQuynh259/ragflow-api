"""Unit tests for RAGChatOrchestratorService."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from chat_api.modules.chat_sessions.domain.entity import ChatSession
from chat_api.modules.messages.application.services import RAGChatOrchestratorService
from chat_api.modules.messages.domain.entity import MessageRole


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
            }
        ],
        {"prompt_tokens": 120, "completion_tokens": 40},
    )

    service = RAGChatOrchestratorService(uow, rag_engine)
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

    # Verify uow tracking
    uow.track.assert_called_once_with(result.user_message, result.assistant_message)
    rag_engine.answer.assert_called_once_with(
        query="What is the policy?",
        document_ids=[str(doc_id)],
        top_k=3,
    )
