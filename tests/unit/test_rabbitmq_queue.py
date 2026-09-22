"""Unit tests for RabbitMQQueueAdapter."""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

from core.queue.rabbitmq import RabbitMQQueueAdapter


def test_rabbitmq_adapter_initialization():
    adapter = RabbitMQQueueAdapter(
        amqp_url="amqp://test:test@rabbitmq:5672/",
        exchange="custom.exchange",
        queue_name="custom.queue",
        routing_key="custom.key",
    )
    assert adapter.amqp_url == "amqp://test:test@rabbitmq:5672/"
    assert adapter.exchange == "custom.exchange"
    assert adapter.queue_name == "custom.queue"
    assert adapter.routing_key == "custom.key"


@patch("pika.BlockingConnection")
def test_rabbitmq_adapter_enqueue_ingestion(mock_blocking_conn):
    mock_conn = MagicMock()
    mock_channel = MagicMock()
    mock_conn.channel.return_value = mock_channel
    mock_conn.is_open = True
    mock_conn.is_closed = False
    mock_blocking_conn.return_value = mock_conn

    adapter = RabbitMQQueueAdapter(
        amqp_url="amqp://guest:guest@localhost:5672/",
        exchange="rag.direct",
        queue_name="rag.document.ingestion",
        routing_key="document.ingestion",
        auto_close=False,
    )

    doc_id = uuid.uuid4()
    job_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    storage_uri = "output/storage/doc.pdf"

    adapter.enqueue_ingestion(
        document_id=doc_id,
        job_id=job_id,
        storage_uri=storage_uri,
        workspace_id=ws_id,
    )

    # Verify exchange declared
    mock_channel.exchange_declare.assert_called_once_with(
        exchange="rag.direct",
        exchange_type="direct",
        durable=True,
    )

    # Verify basic_publish called
    mock_channel.basic_publish.assert_called_once()
    call_kwargs = mock_channel.basic_publish.call_args.kwargs
    assert call_kwargs["exchange"] == "rag.direct"
    assert call_kwargs["routing_key"] == "document.ingestion"

    # Verify payload format
    payload = json.loads(call_kwargs["body"].decode("utf-8"))
    assert payload["document_id"] == str(doc_id)
    assert payload["job_id"] == str(job_id)
    assert payload["storage_uri"] == storage_uri
    assert payload["workspace_id"] == str(ws_id)
    assert payload["action"] == "index"
    assert "enqueued_at" in payload

    # Verify connection remains open for reuse, then closed on adapter.close()
    assert adapter.check_health() is True
    adapter.close()
    mock_conn.close.assert_called_once()


@patch("pika.BlockingConnection")
def test_rabbitmq_adapter_setup_queues_3tier(mock_blocking_conn):
    mock_conn = MagicMock()
    mock_channel = MagicMock()
    mock_conn.channel.return_value = mock_channel
    mock_conn.is_open = True
    mock_blocking_conn.return_value = mock_conn

    adapter = RabbitMQQueueAdapter()
    adapter.setup_queues()

    # Verify 3-tier topology declared: primary, retry, and dlx
    assert mock_channel.exchange_declare.call_count == 3
    # Verify 3 queues declared: primary, retry, and dlq
    assert mock_channel.queue_declare.call_count == 3
    # Verify 3 queue binds: primary, retry, and dlq
    assert mock_channel.queue_bind.call_count == 3

    mock_conn.close.assert_called_once()


@patch("pika.BlockingConnection")
def test_rabbitmq_adapter_general_enqueue(mock_blocking_conn):
    mock_conn = MagicMock()
    mock_channel = MagicMock()
    mock_conn.channel.return_value = mock_channel
    mock_conn.is_open = True
    mock_blocking_conn.return_value = mock_conn

    adapter = RabbitMQQueueAdapter(auto_close=True)
    job_id = adapter.enqueue(
        action="custom_task",
        payload={"task_data": 42},
        correlation_id="corr-123",
    )
    assert job_id is not None
    mock_channel.basic_publish.assert_called_once()
    mock_conn.close.assert_called_once()


@patch("pika.BlockingConnection")
def test_rabbitmq_adapter_health_check(mock_blocking_conn):
    mock_conn = MagicMock()
    mock_conn.is_open = True
    mock_blocking_conn.return_value = mock_conn

    adapter = RabbitMQQueueAdapter(auto_close=True)
    assert adapter.check_health() is True
