"""Event publisher implementations for real-time event distribution."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import pika

from core.config import settings
from core.events.port import EventPublisherPort
from core.events.schema import RealtimeEvent

logger = logging.getLogger(__name__)


class RabbitMQEventPublisher(EventPublisherPort):
    """RabbitMQ Topic Exchange adapter for broadcasting real-time events."""

    def __init__(
        self,
        amqp_url: str | None = None,
        exchange: str | None = None,
    ) -> None:
        self.amqp_url = amqp_url or getattr(
            settings, "RABBITMQ_URL", "amqp://guest:guest@localhost:5672/"
        )
        self.exchange = exchange or getattr(settings, "RABBITMQ_EVENTS_EXCHANGE", "rag.events")
        self._connection: pika.BlockingConnection | None = None
        self._channel: Any = None

    def _get_channel(self) -> Any:
        if self._connection is None or self._connection.is_closed:
            parameters = pika.URLParameters(self.amqp_url)
            self._connection = pika.BlockingConnection(parameters)
            self._channel = self._connection.channel()
            # Ensure the topic exchange exists for real-time broadcast
            self._channel.exchange_declare(
                exchange=self.exchange,
                exchange_type="topic",
                durable=True,
            )
        return self._channel

    def publish(self, event: RealtimeEvent, routing_key: str | None = None) -> None:
        """Publish real-time event to RabbitMQ topic exchange."""
        if not routing_key:
            ws_part = event.workspace_id or "global"
            routing_key = f"workspace.{ws_part}.{event.event}"

        payload_bytes = json.dumps(event.to_dict(), ensure_ascii=False).encode("utf-8")

        try:
            channel = self._get_channel()
            channel.basic_publish(
                exchange=self.exchange,
                routing_key=routing_key,
                body=payload_bytes,
                properties=pika.BasicProperties(
                    content_type="application/json",
                    message_id=event.id,
                    delivery_mode=1,  # Transient (non-persistent) for real-time broadcast
                ),
            )
            logger.debug(
                "Published realtime event '%s' to exchange '%s' [key: %s]",
                event.event,
                self.exchange,
                routing_key,
            )
        except Exception as exc:
            logger.warning("Failed to publish realtime event to RabbitMQ: %s", exc)
            self.close()

    def close(self) -> None:
        if self._connection and not self._connection.is_closed:
            try:
                self._connection.close()
            except Exception:
                pass
        self._connection = None
        self._channel = None


class InMemoryEventPublisher(EventPublisherPort):
    """In-memory event hub for unit tests and local development."""

    def __init__(self) -> None:
        self.published_events: list[RealtimeEvent] = []
        self._subscribers: dict[str, list[asyncio.Queue[RealtimeEvent]]] = {}

    def subscribe(self, workspace_id: str | None = None) -> asyncio.Queue[RealtimeEvent]:
        """Subscribe to events for a specific workspace or all events if workspace_id is None."""
        key = workspace_id or "*"
        queue: asyncio.Queue[RealtimeEvent] = asyncio.Queue()
        self._subscribers.setdefault(key, []).append(queue)
        return queue

    def unsubscribe(
        self, queue: asyncio.Queue[RealtimeEvent], workspace_id: str | None = None
    ) -> None:
        """Unsubscribe a queue from event broadcasts."""
        key = workspace_id or "*"
        if key in self._subscribers and queue in self._subscribers[key]:
            self._subscribers[key].remove(queue)

    def publish(self, event: RealtimeEvent, routing_key: str | None = None) -> None:
        """Record and fan-out event to active in-memory subscriber queues."""
        self.published_events.append(event)

        # Notify specific workspace subscribers
        target_keys = ["*"]
        if event.workspace_id:
            target_keys.append(event.workspace_id)

        for key in target_keys:
            for queue in self._subscribers.get(key, []):
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    pass

    def clear(self) -> None:
        """Clear recorded events and subscribers (useful between test cases)."""
        self.published_events.clear()
        self._subscribers.clear()


__all__ = [
    "RabbitMQEventPublisher",
    "InMemoryEventPublisher",
]
