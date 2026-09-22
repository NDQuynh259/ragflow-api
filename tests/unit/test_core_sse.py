"""Unit tests for Core Server-Sent Events (SSE) Engine."""

from __future__ import annotations

import asyncio
import uuid

import pytest

from core.sse import (
    SSEHub,
    SSEMessage,
    SSEResponse,
    chat_done_message,
    chat_token_message,
    document_failed_message,
    document_progress_message,
    document_ready_message,
    ping_message,
    sse_event_stream,
)


def test_sse_message_encoding_basic():
    msg = SSEMessage(
        event="document_progress",
        data={"percent": 50, "step": "parsing"},
        id="evt-123",
        retry=3000,
    )
    encoded = msg.encode()
    expected = (
        "id: evt-123\n"
        "event: document_progress\n"
        "retry: 3000\n"
        'data: {"percent": 50, "step": "parsing"}\n\n'
    )
    assert encoded == expected


def test_sse_message_multiline():
    msg = SSEMessage(event="chunk", data="first line\nsecond line\nthird line")
    encoded = msg.encode()
    assert "data: first line\ndata: second line\ndata: third line\n\n" in encoded


def test_sse_ping_message():
    ping = ping_message()
    assert ping.encode() == ": ping\n\n"


def test_sse_domain_helpers():
    ws_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    job_id = uuid.uuid4()

    progress = document_progress_message(ws_id, doc_id, job_id, step="chunking", percent=65)
    assert progress.event == "document_progress"
    assert progress.data["percent"] == 65

    ready = document_ready_message(ws_id, doc_id, job_id, pages=15, chunks=40)
    assert ready.event == "document_ready"
    assert ready.data["pages"] == 15

    failed = document_failed_message(ws_id, doc_id, job_id, error="File broken")
    assert failed.event == "document_failed"
    assert failed.data["error"] == "File broken"

    token = chat_token_message(ws_id, uuid.uuid4(), uuid.uuid4(), delta="Hello")
    assert token.event == "chat_token"
    assert token.data["delta"] == "Hello"

    done = chat_done_message(ws_id, uuid.uuid4(), uuid.uuid4(), citations=[{"id": 1}])
    assert done.event == "chat_done"
    assert len(done.data["citations"]) == 1


@pytest.mark.anyio
async def test_sse_stream_yields_message_and_ping():
    queue: asyncio.Queue[SSEMessage] = asyncio.Queue()
    msg = SSEMessage(event="test", data="content")
    await queue.put(msg)

    stream = sse_event_stream(queue, ping_interval=0.05)

    # First item should be the message
    item1 = await anext(stream)
    assert "event: test" in item1
    assert "data: content" in item1

    # Second item should be a keepalive ping because queue is empty
    item2 = await anext(stream)
    assert item2 == ": ping\n\n"


@pytest.mark.anyio
async def test_sse_hub_pub_sub():
    hub = SSEHub(enable_rabbitmq=False)
    ws_1 = str(uuid.uuid4())
    ws_2 = str(uuid.uuid4())

    q_ws1 = hub.subscribe(ws_1)
    q_all = hub.subscribe(None)

    msg_1 = SSEMessage(event="evt1", data="for ws1", workspace_id=ws_1)
    msg_2 = SSEMessage(event="evt2", data="for ws2", workspace_id=ws_2)

    hub.publish(msg_1)
    hub.publish(msg_2)

    assert q_ws1.qsize() == 1
    assert (await q_ws1.get()).event == "evt1"

    assert q_all.qsize() == 2
    assert (await q_all.get()).event == "evt1"
    assert (await q_all.get()).event == "evt2"

    hub.unsubscribe(q_ws1, ws_1)
    hub.publish(msg_1)
    assert q_ws1.qsize() == 0


def test_sse_response_headers():
    async def dummy_gen():
        yield "data: hello\n\n"

    response = SSEResponse(content=dummy_gen())
    assert response.media_type == "text/event-stream"
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
    assert response.headers["cache-control"] == "no-cache, no-transform"
    assert response.headers["connection"] == "keep-alive"
    assert response.headers["x-accel-buffering"] == "no"
