"""Unit tests for worker dispatcher and processors."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from worker.bus import get_worker_command_bus
from worker.dispatcher import build_dispatcher
from worker.handlers.index_document import IndexDocumentCommand, IndexDocumentHandler
from worker.processors.index_document import process_index_document

from core.queue import Actions


def test_build_dispatcher_registers_expected_actions() -> None:
    dispatcher = build_dispatcher()
    assert Actions.INDEX in dispatcher._handlers
    assert Actions.REINDEX in dispatcher._handlers
    assert "unknown_action" not in dispatcher._handlers


def test_process_index_document_dispatches_via_command_bus() -> None:
    job_id = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())
    ws_id = str(uuid.uuid4())
    uri = "storage://documents/sample.pdf"

    mock_bus = MagicMock()
    mock_bus.execute.return_value = 42

    with patch("worker.processors.index_document.get_worker_command_bus", return_value=mock_bus):
        result = process_index_document(
            job_id=job_id,
            document_id=doc_id,
            workspace_id=ws_id,
            storage_uri=uri,
        )
        assert result == 42
        mock_bus.execute.assert_called_once()
        cmd = mock_bus.execute.call_args[0][0]
        assert isinstance(cmd, IndexDocumentCommand)
        assert str(cmd.job_id) == job_id
        assert str(cmd.document_id) == doc_id
        assert str(cmd.workspace_id) == ws_id
        assert cmd.storage_uri == uri


@patch("worker.bus.get_rag_engine")
@patch("worker.bus.get_storage")
@patch("worker.bus.get_document_pipeline")
@patch("worker.bus.get_uow")
def test_get_worker_command_bus_execution(
    mock_get_uow: MagicMock,
    mock_get_pipeline: MagicMock,
    mock_get_storage: MagicMock,
    mock_get_engine: MagicMock,
) -> None:
    bus = get_worker_command_bus()

    cmd = IndexDocumentCommand(
        job_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        storage_uri="uri",
    )

    with patch.object(IndexDocumentHandler, "handle", return_value=99) as mock_handle:
        result = bus.execute(cmd)
        assert result == 99
        mock_handle.assert_called_once_with(cmd)
