"""Unified Background Worker consuming from RabbitMQ."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import aio_pika
from pamqp.common import FieldValue

from core.config import settings
from core.logging import setup_logging
from worker.processors.index_document import process_index_document

logger = logging.getLogger("worker")


async def run_worker() -> None:
    setup_logging()
    amqp_url = getattr(settings, "RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
    exchange_name = getattr(settings, "RABBITMQ_EXCHANGE", "rag.direct")
    queue_name = getattr(settings, "RABBITMQ_INGESTION_QUEUE", "rag.document.ingestion")
    routing_key = getattr(settings, "RABBITMQ_ROUTING_KEY", "document.ingestion")

    logger.info("Connecting to RabbitMQ at %s...", amqp_url)
    connection = await aio_pika.connect_robust(amqp_url)

    async with connection:
        channel = await connection.channel()

        # 1. Setup Dead Letter Exchange and Queue
        dlx_exchange_name = f"{exchange_name}.dlx"
        dlq_queue_name = f"{queue_name}.dlq"
        dlq_routing_key = f"{routing_key}.dlq"

        dlx = await channel.declare_exchange(
            dlx_exchange_name, type=aio_pika.ExchangeType.DIRECT, durable=True
        )
        dlq = await channel.declare_queue(dlq_queue_name, durable=True)
        await dlq.bind(dlx, routing_key=dlq_routing_key)

        # 2. Setup Primary Exchange and Queue with DLX
        exchange = await channel.declare_exchange(
            exchange_name, type=aio_pika.ExchangeType.DIRECT, durable=True
        )
        queue_args: dict[str, FieldValue] = {
            "x-dead-letter-exchange": dlx_exchange_name,
            "x-dead-letter-routing-key": dlq_routing_key,
        }
        queue = await channel.declare_queue(queue_name, durable=True, arguments=queue_args)
        await queue.bind(exchange, routing_key=routing_key)

        # Set prefetch count to 1 (fair dispatch: process one job at a time per worker process)
        await channel.set_qos(prefetch_count=1)

        logger.info(
            "Worker ready. Listening on queue '%s' (exchange: '%s', routing: '%s')...",
            queue_name,
            exchange_name,
            routing_key,
        )

        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process(requeue=False):
                    try:
                        raw_body = message.body.decode("utf-8")
                        payload: dict[str, Any] = json.loads(raw_body)

                        action = payload.get("action", "index")
                        job_id = payload.get("job_id", "")
                        doc_id = payload.get("document_id", "")
                        storage_uri = payload.get("storage_uri", "")
                        workspace_id = payload.get("workspace_id", "")

                        logger.info(
                            "Received message: action=%s, job=%s, doc=%s", action, job_id, doc_id
                        )

                        # Dispatch to appropriate processor
                        if action in ("index", "reindex"):
                            indexed = await asyncio.to_thread(
                                process_index_document,
                                job_id=job_id,
                                document_id=doc_id,
                                storage_uri=storage_uri,
                                workspace_id=workspace_id,
                            )
                            logger.info("Job %s completed: %d chunks indexed.", job_id, indexed)
                        else:
                            logger.warning("Unknown action '%s', skipping message.", action)

                    except Exception as exc:
                        logger.exception("Error processing message: %s", exc)
                        # The context manager with requeue=False routes the message to DLQ
                        raise


def main() -> None:
    try:
        asyncio.run(run_worker())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Worker stopped by user.")


if __name__ == "__main__":
    main()
