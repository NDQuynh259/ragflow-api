"""Unit tests for IndexDocumentHandler."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from worker.handlers.index_document import IndexDocumentCommand, IndexDocumentHandler


def test_index_document_handler_success() -> None:
    job_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    storage_uri = "storage://documents/sample.pdf"

    # Mock UnitOfWork and Session
    uow = MagicMock()
    session = MagicMock()
    uow.session = session

    # 1. State gate update (rowcount = 1 -> claimed)
    gate_result = MagicMock()
    gate_result.rowcount = 1

    # 2. Select document query returns (doc_id, "test.pdf", storage_uri, "queued")
    doc_select_result = MagicMock()
    doc_select_result.fetchone.return_value = (doc_id, "test.pdf", storage_uri, "queued")

    session.execute.side_effect = [
        gate_result,  # UPDATE ingestion_jobs ... status = 'running'
        doc_select_result,  # SELECT id, filename ...
        MagicMock(),  # UPDATE documents SET status = 'processing'
        MagicMock(),  # UPDATE ingestion_jobs ... status = 'completed'
        MagicMock(),  # UPDATE documents SET status = 'ready'
    ]

    # Mock Storage
    storage = MagicMock()
    storage.get.return_value = b"%PDF-1.4 sample content"

    # Mock Pipeline
    pipeline = MagicMock()
    mock_chunk = MagicMock()
    mock_processed = MagicMock(page_count=2, chunks=[mock_chunk])
    pipeline.process.return_value = mock_processed

    # Mock Engine
    engine = MagicMock()
    engine.index.return_value = 1

    handler = IndexDocumentHandler(
        uow=uow,
        storage=storage,
        pipeline=pipeline,
        engine=engine,
    )

    cmd = IndexDocumentCommand(
        job_id=job_id,
        document_id=doc_id,
        workspace_id=ws_id,
        storage_uri=storage_uri,
    )

    result = handler.handle(cmd)

    assert result == 1
    assert mock_chunk.workspace_id == str(ws_id)
    storage.get.assert_called_once_with(storage_uri)
    pipeline.process.assert_called_once_with(
        b"%PDF-1.4 sample content",
        filename="test.pdf",
        document_id=str(doc_id),
    )
    engine.index.assert_called_once_with([mock_chunk])


def test_index_document_handler_skips_when_already_running() -> None:
    job_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    ws_id = uuid.uuid4()

    uow = MagicMock()
    session = MagicMock()
    uow.session = session

    gate_result = MagicMock()
    gate_result.rowcount = 0  # Not updated because status already running

    status_check = MagicMock()
    status_check.fetchone.return_value = ("running",)

    session.execute.side_effect = [gate_result, status_check]

    storage = MagicMock()
    pipeline = MagicMock()
    engine = MagicMock()

    handler = IndexDocumentHandler(
        uow=uow,
        storage=storage,
        pipeline=pipeline,
        engine=engine,
    )

    cmd = IndexDocumentCommand(
        job_id=job_id,
        document_id=doc_id,
        workspace_id=ws_id,
        storage_uri="uri",
    )

    result = handler.handle(cmd)
    assert result == 0
    storage.get.assert_not_called()
    pipeline.process.assert_not_called()
