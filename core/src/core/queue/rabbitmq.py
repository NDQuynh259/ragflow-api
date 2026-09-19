"""RabbitMQ message queue adapter for dispatching background jobs to workers."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import pika

from core.config import settings
from core.queue.port import IngestionQueuePort
from core.uuid7 import uuid7_str

logger = logging.getLogger(__name__)


class RabbitMQQueueAdapter(IngestionQueuePort):
    """Production RabbitMQ adapter for publishing background jobs and document ingestion tasks."""

    def __init__(
        self,
        amqp_url: str | None = None,
        exchange: str | None = None,
        queue_name: str | None = None,
        routing_key: str | None = None,
    ) -> None:
        self.amqp_url = amqp_url or getattr(
            settings, "RABBITMQ_URL", "amqp://guest:guest@localhost:5672/"
        )
        self.exchange = exchange or getattr(settings, "RABBITMQ_EXCHANGE", "rag.direct")
        self.queue_name = queue_name or getattr(
            settings, "RABBITMQ_INGESTION_QUEUE", "rag.document.ingestion"
        )
        self.routing_key = routing_key or getattr(
            settings, "RABBITMQ_ROUTING_KEY", "document.ingestion"
        )
        self._connection: pika.BlockingConnection | None = None
        self._channel: Any = None

    def _get_channel(self) -> Any:
        if self._connection is None or self._connection.is_closed:
            parameters = pika.URLParameters(self.amqp_url)
            self._connection = pika.BlockingConnection(parameters)
            self._channel = self._connection.channel()
            # Ensure exchange exists
            self._channel.exchange_declare(
                exchange=self.exchange,
                exchange_type="direct",
                durable=True,
            )
        return self._channel

    def setup_queues(self) -> None:
        """Declare exchanges, queues, and dead-letter routing in RabbitMQ."""
        connection = pika.BlockingConnection(pika.URLParameters(self.amqp_url))
        try:
            channel = connection.channel()

            # 1. Setup Dead Letter Exchange and Queue
            dlx_exchange = f"{self.exchange}.dlx"
            dlq_queue = f"{self.queue_name}.dlq"
            dlq_routing_key = f"{self.routing_key}.dlq"

            channel.exchange_declare(exchange=dlx_exchange, exchange_type="direct", durable=True)
            channel.queue_declare(queue=dlq_queue, durable=True)
            channel.queue_bind(exchange=dlx_exchange, queue=dlq_queue, routing_key=dlq_routing_key)

            # 2. Setup Primary Direct Exchange and Queue with DLX configuration
            channel.exchange_declare(exchange=self.exchange, exchange_type="direct", durable=True)
            queue_args: dict[str, Any] = {
                "x-dead-letter-exchange": dlx_exchange,
                "x-dead-letter-routing-key": dlq_routing_key,
            }
            channel.queue_declare(queue=self.queue_name, durable=True, arguments=queue_args)
            channel.queue_bind(
                exchange=self.exchange, queue=self.queue_name, routing_key=self.routing_key
            )
            logger.info(
                "RabbitMQ exchange '%s' and queue '%s' declared successfully.",
                self.exchange,
                self.queue_name,
            )
        finally:
            if connection.is_open:
                connection.close()

    def enqueue(
        self,
        action: str,
        payload: dict[str, Any],
        job_id: str | uuid.UUID | None = None,
        routing_key: str | None = None,
    ) -> str:
        """Enqueue an arbitrary background job action to RabbitMQ."""
        resolved_job_id = str(job_id) if job_id else uuid7_str()
        resolved_key = routing_key or self.routing_key

        full_payload: dict[str, Any] = {
            "job_id": resolved_job_id,
            "action": action,
            "enqueued_at": datetime.now(UTC).isoformat(),
            **payload,
        }
        body = json.dumps(full_payload, ensure_ascii=False).encode("utf-8")

        properties = pika.BasicProperties(
            delivery_mode=pika.DeliveryMode.Persistent,
            content_type="application/json",
            message_id=resolved_job_id,
            timestamp=int(datetime.now(UTC).timestamp()),
        )

        try:
            channel = self._get_channel()
            channel.basic_publish(
                exchange=self.exchange,
                routing_key=resolved_key,
                body=body,
                properties=properties,
            )
            logger.info(
                "Enqueued job %s (action: %s) to RabbitMQ exchange '%s' [routing: '%s']",
                resolved_job_id,
                action,
                self.exchange,
                resolved_key,
            )
        except Exception as exc:
            logger.warning("Failed to publish to RabbitMQ, attempting reconnect: %s", exc)
            self.close()
            # Retry once with fresh connection
            channel = self._get_channel()
            channel.basic_publish(
                exchange=self.exchange,
                routing_key=resolved_key,
                body=body,
                properties=properties,
            )

        return resolved_job_id

    def enqueue_ingestion(
        self,
        document_id: uuid.UUID,
        job_id: uuid.UUID,
        storage_uri: str,
        workspace_id: uuid.UUID,
    ) -> None:
        """Enqueue document ingestion job (implements IngestionQueuePort)."""
        self.enqueue(
            action="index",
            payload={
                "document_id": str(document_id),
                "storage_uri": storage_uri,
                "workspace_id": str(workspace_id),
            },
            job_id=job_id,
            routing_key=self.routing_key,
        )

    def check_health(self) -> bool:
        """Ping RabbitMQ connection to verify liveness."""
        try:
            channel = self._get_channel()
            return bool(channel and channel.is_open)
        except Exception:
            return False

    def close(self) -> None:
        """Close connection and channel."""
        if self._connection and not self._connection.is_closed:
            try:
                self._connection.close()
            except Exception:
                pass
        self._connection = None
        self._channel = None


__all__ = ["RabbitMQQueueAdapter"]
