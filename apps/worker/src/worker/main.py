"""Unified Background Worker consuming from RabbitMQ using JobDispatcher and AsyncRabbitMQConsumer."""

from __future__ import annotations

import asyncio
import logging

from core.logging import setup_logging
from core.queue import AsyncRabbitMQConsumer
from worker.dispatcher import build_dispatcher

logger = logging.getLogger("worker")


async def run_worker() -> None:
    """Initialize logging, setup dispatcher, and start robust RabbitMQ consumer."""
    setup_logging()
    dispatcher = build_dispatcher()
    consumer = AsyncRabbitMQConsumer(dispatcher=dispatcher)

    logger.info("Starting background ingestion worker...")
    await consumer.run()


def main() -> None:
    try:
        asyncio.run(run_worker())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Worker stopped by user.")


if __name__ == "__main__":
    main()
