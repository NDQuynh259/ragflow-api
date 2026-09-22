"""Unit tests for Core Realtime and Server-Sent Events (SSE) foundation."""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

from core.events import (
    InMemoryEventPublisher,
    RabbitMQEventPublisher,
    RealtimeEvent,
    create_chat_done_event,
    create_chat_token_event,
    create_document_failed_event,
    create_document_progress_event,
    create_document_ready_event,
    format_ping,
    format_sse,
)


def test_format_sse_basic():
    formatted = format_sse(event="test_event", data={"key": "value"}, event_id="123", retry=3000)
    expected = 'id: 123\nevent: test_event\nretry: 3000\ndata: {"key": "value"}\n\n'
    assert formatted == expected


def test_format_sse_multiline_data():
    multiline_text = "line1\nline2\nline3"
    formatted = format_sse(event="multiline", data=multiline_text)
    expected = "event: multiline\ndata: line1\ndata: line2\ndata: line3\n\n"
    assert formatted == expected


def test_format_ping():
    assert format_ping() == ": ping\n\n"
    assert format_ping("custom-heartbeat") == ": custom-heartbeat\n\n"


def test_realtime_event_serialization():
    ws_id = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())

    event = create_document_progress_event(
        workspace_id=ws_id,
        document_id=doc_id,
        job_id=job_id,
        step="parsing",
        percent=40,
        details="Parsing page 2/5",
    )

    assert event.event == "document_progress"
    assert event.workspace_id == ws_id
    assert event.data["percent"] == 40
    assert event.data["step"] == "parsing"

    sse_text = event.to_sse()
    assert f"id: {event.id}" in sse_text
    assert "event: document_progress" in sse_text
    assert '"step": "parsing"' in sse_text
    assert sse_text.endswith("\n\n")


def test_domain_event_factories():
    ws_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    job_id = uuid.uuid4()

    ready_event = create_document_ready_event(ws_id, doc_id, job_id, pages=10, chunks=25)
    assert ready_event.event == "document_ready"
    assert ready_event.data["pages"] == 10
    assert ready_event.data["chunks"] == 25
    assert ready_event.data["percent"] == 100

    failed_event = create_document_failed_event(ws_id, doc_id, job_id, error="Corrupt PDF")
    assert failed_event.event == "document_failed"
    assert failed_event.data["error"] == "Corrupt PDF"

    chat_token_event = create_chat_token_event(ws_id, uuid.uuid4(), uuid.uuid4(), delta="Hello ")
    assert chat_token_event.event == "chat_token"
    assert chat_token_event.data["delta"] == "Hello "

    chat_done_event = create_chat_done_event(
        ws_id, uuid.uuid4(), uuid.uuid4(), citations=[{"chunk_id": "c1"}]
    )
    assert chat_done_event.event == "chat_done"
    assert len(chat_done_event.data["citations"]) == 1


def test_in_memory_event_publisher():
    publisher = InMemoryEventPublisher()
    ws_1 = str(uuid.uuid4())
    ws_2 = str(uuid.uuid4())

    q_ws1 = publisher.subscribe(ws_1)
    q_global = publisher.subscribe(None)  # listens to all events

    event_ws1 = RealtimeEvent(event="evt1", data="hello ws1", workspace_id=ws_1)
    event_ws2 = RealtimeEvent(event="evt2", data="hello ws2", workspace_id=ws_2)

    publisher.publish(event_ws1)
    publisher.publish(event_ws2)

    # q_ws1 should only have received event_ws1
    assert q_ws1.qsize() == 1
    received_ws1 = q_ws1.get_nowait()
    assert received_ws1.event == "evt1"

    # q_global should have received both
    assert q_global.qsize() == 2
    assert q_global.get_nowait().event == "evt1"
    assert q_global.get_nowait().event == "evt2"

    # Test unsubscribe
    publisher.unsubscribe(q_ws1, ws_1)
    publisher.publish(event_ws1)
    assert q_ws1.qsize() == 0  # No new events received after unsubscribe


@patch("pika.BlockingConnection")
def test_rabbitmq_event_publisher(mock_blocking_conn):
    mock_conn = MagicMock()
    mock_channel = MagicMock()
    mock_conn.channel.return_value = mock_channel
    mock_conn.is_closed = False
    mock_blocking_conn.return_value = mock_conn

    publisher = RabbitMQEventPublisher(
        amqp_url="amqp://test:test@rabbitmq:5672/",
        exchange="custom.events",
    )

    event = RealtimeEvent(
        event="document_ready",
        workspace_id="ws-999",
        data={"pages": 5},
    )

    publisher.publish(event)

    # Verify exchange declared
    mock_channel.exchange_declare.assert_called_once_with(
        exchange="custom.events",
        exchange_type="topic",
        durable=True,
    )

    # Verify published
    mock_channel.basic_publish.assert_called_once()
    _, kwargs = mock_channel.basic_publish.call_args
    assert kwargs["exchange"] == "custom.events"
    assert kwargs["routing_key"] == "workspace.ws-999.document_ready"
    assert json.loads(kwargs["body"].decode("utf-8"))["event"] == "document_ready"

    publisher.close()
    mock_conn.close.assert_called_once()
