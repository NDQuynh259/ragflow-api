"""Unit tests for Message Queue Core (JobEnvelope, Dispatcher, InMemoryAdapter, Ports)."""

from __future__ import annotations

import asyncio
import uuid

import pytest

from core.queue.constants import Actions
from core.queue.consumer import JobDispatcher
from core.queue.in_memory import InMemoryQueueAdapter
from core.queue.port import IngestionQueuePort, JobQueuePort
from core.queue.schema import DocumentJobPayload, JobEnvelope


def test_job_envelope_serialization():
    payload = {"document_id": "doc-1", "workspace_id": "ws-1"}
    envelope = JobEnvelope(
        action="index",
        payload=payload,
        correlation_id="corr-999",
    )

    data_json = envelope.to_json()
    assert "corr-999" in data_json
    assert "index" in data_json

    # Roundtrip from JSON
    restored = JobEnvelope.from_json(data_json)
    assert restored.job_id == envelope.job_id
    assert restored.action == envelope.action
    assert restored.payload["document_id"] == "doc-1"
    assert restored.correlation_id == "corr-999"

    # Bytes roundtrip
    bytes_data = envelope.to_bytes()
    assert isinstance(bytes_data, bytes)
    restored_bytes = JobEnvelope.from_bytes(bytes_data)
    assert restored_bytes.job_id == envelope.job_id


def test_document_job_payload():
    doc_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    payload = DocumentJobPayload.create(
        document_id=doc_id,
        storage_uri="output/file.pdf",
        workspace_id=ws_id,
    )
    d = payload.to_dict()
    assert d["document_id"] == str(doc_id)
    assert d["workspace_id"] == str(ws_id)
    assert d["storage_uri"] == "output/file.pdf"


def test_in_memory_queue_adapter():
    adapter = InMemoryQueueAdapter()
    assert adapter.check_health() is True

    # Enqueue general job
    job1 = adapter.enqueue(action="index", payload={"k": 1}, correlation_id="c1")
    _job2 = adapter.enqueue(action="delete", payload={"k": 2})

    assert len(adapter.enqueued_jobs) == 2
    index_jobs = adapter.get_jobs_for_action("index")
    assert len(index_jobs) == 1
    assert index_jobs[0].job_id == job1

    # Enqueue ingestion
    doc_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    job3 = uuid.uuid4()
    adapter.enqueue_ingestion(
        document_id=doc_id,
        job_id=job3,
        storage_uri="uri",
        workspace_id=ws_id,
    )
    assert len(adapter.enqueued_jobs) == 3

    adapter.clear()
    assert len(adapter.enqueued_jobs) == 0


def test_ingestion_queue_port_backward_compatibility():
    """Verify that a legacy subclass implementing ONLY enqueue_ingestion can be instantiated."""

    class LegacyFakeQueue(IngestionQueuePort):
        def __init__(self):
            self.records = []

        def enqueue_ingestion(self, document_id, job_id, storage_uri, workspace_id):
            self.records.append((document_id, job_id, storage_uri, workspace_id))

    fake = LegacyFakeQueue()
    assert isinstance(fake, JobQueuePort)

    # Calling enqueue_ingestion works
    d_id = uuid.uuid4()
    j_id = uuid.uuid4()
    w_id = uuid.uuid4()
    fake.enqueue_ingestion(d_id, j_id, "uri", w_id)
    assert len(fake.records) == 1

    # Calling generic enqueue with action="index" routes to enqueue_ingestion
    fake.enqueue(
        action=Actions.INDEX,
        payload={"document_id": str(d_id), "workspace_id": str(w_id), "storage_uri": "uri2"},
        job_id=j_id,
    )
    assert len(fake.records) == 2


def test_job_dispatcher_sync_and_async_handlers():
    dispatcher = JobDispatcher()
    called_sync = []
    called_async = []

    def sync_handler(job_id: str, value: int) -> int:
        called_sync.append((job_id, value))
        return value * 2

    async def async_handler(envelope: JobEnvelope) -> str:
        called_async.append(envelope.job_id)
        return "async_ok"

    dispatcher.register("sync_action", sync_handler)
    dispatcher.register("async_action", async_handler)

    async def run_test():
        # Test sync dispatch
        envelope_sync = JobEnvelope(
            action="sync_action",
            payload={"value": 10, "extra_ignored": True},
        )
        res_sync = await dispatcher.dispatch(envelope_sync)
        assert res_sync == 20
        assert called_sync == [(envelope_sync.job_id, 10)]

        # Test async dispatch
        envelope_async = JobEnvelope(
            action="async_action",
            payload={"data": "test"},
        )
        res_async = await dispatcher.dispatch(envelope_async)
        assert res_async == "async_ok"
        assert called_async == [envelope_async.job_id]

    asyncio.run(run_test())


def test_job_dispatcher_unknown_action():
    dispatcher = JobDispatcher()
    envelope = JobEnvelope(action="unknown_action", payload={})

    async def run_test():
        with pytest.raises(ValueError, match="No handler registered for action 'unknown_action'"):
            await dispatcher.dispatch(envelope)

    asyncio.run(run_test())
