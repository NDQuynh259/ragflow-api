"""RabbitMQ message queue adapter for dispatching document ingestion jobs."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import pika

from core.config import settings
from core.queue.port import IngestionQueuePort

logger = logging.getLogger(__name__)


class RabbitMQQueueAdapter(IngestionQueuePort):
    """Production RabbitMQ adapter for publishing document ingestion jobs."""

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

    def _get_connection(self) -> pika.BlockingConnection:
        parameters = pika.URLParameters(self.amqp_url)
        return pika.BlockingConnection(parameters)

    def setup_queues(self) -> None:
        """Declare exchanges, queues, and dead-letter routing in RabbitMQ."""
        connection = self._get_connection()
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

    def enqueue_ingestion(
        self,
        document_id: uuid.UUID,
        job_id: uuid.UUID,
        storage_uri: str,
        workspace_id: uuid.UUID,
    ) -> None:
        payload = {
            "job_id": str(job_id),
            "document_id": str(document_id),
            "storage_uri": storage_uri,
            "workspace_id": str(workspace_id),
            "action": "index",
            "enqueued_at": datetime.now(UTC).isoformat(),
        }
        body = json.dumps(payload).encode("utf-8")

        connection = self._get_connection()
        try:
            channel = connection.channel()

            # Ensure exchange and queue exist
            channel.exchange_declare(exchange=self.exchange, exchange_type="direct", durable=True)

            properties = pika.BasicProperties(
                delivery_mode=pika.DeliveryMode.Persistent,
                content_type="application/json",
                message_id=str(job_id),
                timestamp=int(datetime.now(UTC).timestamp()),
            )

            channel.basic_publish(
                exchange=self.exchange,
                routing_key=self.routing_key,
                body=body,
                properties=properties,
            )

            logger.info(
                "Enqueued ingestion job %s for document %s to RabbitMQ exchange '%s' (routing: '%s')",
                job_id,
                document_id,
                self.exchange,
                self.routing_key,
            )
        finally:
            if connection.is_open:
                connection.close()


__all__ = ["RabbitMQQueueAdapter"]
