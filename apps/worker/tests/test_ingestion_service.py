"""Unit tests for DocumentIngestionService."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from worker.services.ingestion import DocumentIngestionService


def test_document_ingestion_service_execute_pipeline() -> None:
    storage = MagicMock()
    pipeline = MagicMock()
    engine = MagicMock()

    doc_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    storage_uri = "storage://test.pdf"

    storage.get.return_value = b"%PDF dummy content"

    mock_chunk_1 = MagicMock()
    mock_chunk_2 = MagicMock()
    mock_processed = MagicMock(page_count=3, chunks=[mock_chunk_1, mock_chunk_2])
    pipeline.process.return_value = mock_processed

    engine.index.return_value = 2

    service = DocumentIngestionService(storage=storage, pipeline=pipeline, engine=engine)
    result = service.execute_pipeline(
        storage_uri=storage_uri,
        filename="test.pdf",
        document_id=doc_id,
        workspace_id=ws_id,
    )

    assert result.page_count == 3
    assert result.chunk_count == 2
    assert result.file_size == len(b"%PDF dummy content")
    assert result.indexed_count == 2

    assert mock_chunk_1.workspace_id == str(ws_id)
    assert mock_chunk_2.workspace_id == str(ws_id)

    storage.get.assert_called_once_with(storage_uri)
    pipeline.process.assert_called_once_with(
        b"%PDF dummy content",
        filename="test.pdf",
        document_id=str(doc_id),
    )
    engine.index.assert_called_once_with([mock_chunk_1, mock_chunk_2])
