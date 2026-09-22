"""Central Server-Sent Events (SSE) Hub for subscribing and broadcasting events."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import pika

from core.config import settings
from core.sse.message import SSEMessage
from core.sse.response import SSEResponse
from core.sse.stream import sse_event_stream

logger = logging.getLogger(__name__)


class SSEHub:
    """Central manager for Server-Sent Events streams and cross-process broadcasting."""

    def __init__(
        self,
        enable_rabbitmq: bool = True,
        amqp_url: str | None = None,
        exchange: str | None = None,
    ) -> None:
        self.enable_rabbitmq = enable_rabbitmq
        self.amqp_url = amqp_url or getattr(
            settings, "RABBITMQ_URL", "amqp://guest:guest@localhost:5672/"
        )
        self.exchange = exchange or getattr(settings, "RABBITMQ_EVENTS_EXCHANGE", "rag.events")
        self._subscribers: dict[str, list[asyncio.Queue[SSEMessage]]] = {}
        self._rmq_connection: pika.BlockingConnection | None = None
        self._rmq_channel: Any = None

    # --------------------------------------------------------------------------
    # In-Process Subscribers
    # --------------------------------------------------------------------------

    def subscribe(self, workspace_id: str | None = None) -> asyncio.Queue[SSEMessage]:
        """Subscribe an async queue to SSE messages for a given workspace or all workspaces."""
        key = workspace_id or "*"
        queue: asyncio.Queue[SSEMessage] = asyncio.Queue()
        self._subscribers.setdefault(key, []).append(queue)
        logger.debug(
            "Added SSE subscriber for workspace '%s'. Total: %d", key, len(self._subscribers[key])
        )
        return queue

    def unsubscribe(
        self, queue: asyncio.Queue[SSEMessage], workspace_id: str | None = None
    ) -> None:
        """Unsubscribe and remove an async queue."""
        key = workspace_id or "*"
        if key in self._subscribers and queue in self._subscribers[key]:
            self._subscribers[key].remove(queue)
            logger.debug(
                "Removed SSE subscriber for workspace '%s'. Remaining: %d",
                key,
                len(self._subscribers[key]),
            )

    # --------------------------------------------------------------------------
    # Broadcasting & Publishing
    # --------------------------------------------------------------------------

    def _get_rmq_channel(self) -> Any:
        if self._rmq_connection is None or self._rmq_connection.is_closed:
            parameters = pika.URLParameters(self.amqp_url)
            self._rmq_connection = pika.BlockingConnection(parameters)
            self._rmq_channel = self._rmq_connection.channel()
            self._rmq_channel.exchange_declare(
                exchange=self.exchange,
                exchange_type="topic",
                durable=True,
            )
        return self._rmq_channel

    def publish(
        self,
        message: SSEMessage,
        workspace_id: str | None = None,
    ) -> None:
        """Broadcast an SSEMessage to local in-process subscribers and RabbitMQ."""
        target_ws = workspace_id or message.workspace_id

        # 1. Fan-out to local in-process subscriber queues
        keys = ["*"]
        if target_ws:
            keys.append(target_ws)

        for key in keys:
            for q in self._subscribers.get(key, []):
                try:
                    q.put_nowait(message)
                except asyncio.QueueFull:
                    pass

        # 2. Publish to RabbitMQ topic exchange for distributed instances/workers
        if self.enable_rabbitmq:
            routing_key = f"workspace.{target_ws or 'global'}.{message.event or 'message'}"
            try:
                channel = self._get_rmq_channel()
                body = json.dumps(message.to_dict(), ensure_ascii=False).encode("utf-8")
                channel.basic_publish(
                    exchange=self.exchange,
                    routing_key=routing_key,
                    body=body,
                    properties=pika.BasicProperties(
                        content_type="application/json",
                        message_id=message.id,
                        delivery_mode=1,  # Transient for real-time streaming
                    ),
                )
            except Exception as exc:
                logger.debug("RabbitMQ event publish skipped or failed: %s", exc)

    # --------------------------------------------------------------------------
    # FastAPI SSE Stream Helpers
    # --------------------------------------------------------------------------

    async def stream(
        self,
        workspace_id: str | None = None,
        ping_interval: float = 15.0,
    ) -> AsyncIterator[str]:
        """Async generator that handles subscription lifecycle and yields SSE text chunks."""
        queue = self.subscribe(workspace_id)
        try:
            async for chunk in sse_event_stream(queue, ping_interval=ping_interval):
                yield chunk
        finally:
            self.unsubscribe(queue, workspace_id)

    def create_response(
        self,
        workspace_id: str | None = None,
        ping_interval: float = 15.0,
    ) -> SSEResponse:
        """Create a complete FastAPI/Starlette SSEResponse for the specified workspace."""
        return SSEResponse(
            content=self.stream(workspace_id=workspace_id, ping_interval=ping_interval)
        )

    def close(self) -> None:
        """Clean up resources and connections."""
        if self._rmq_connection and not self._rmq_connection.is_closed:
            try:
                self._rmq_connection.close()
            except Exception:
                pass
        self._rmq_connection = None
        self._rmq_channel = None
        self._subscribers.clear()


# Default singleton instance
sse_hub = SSEHub()

__all__ = ["SSEHub", "sse_hub"]
