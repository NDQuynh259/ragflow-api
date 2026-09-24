"""Unified Background Worker consuming from RabbitMQ using JobDispatcher and AsyncRabbitMQConsumer."""

from __future__ import annotations

import asyncio
import logging

from core.config import settings
from core.logging import setup_logging
from core.queue import AsyncRabbitMQConsumer
from worker.dependencies import get_storage_sync_callback, get_storage_sync_service
from worker.dispatcher import build_dispatcher

logger = logging.getLogger("worker")


async def run_worker() -> None:
    """Initialize logging, setup dispatcher, and start robust consumer & sync worker."""
    setup_logging()
    dispatcher = build_dispatcher()
    consumer = AsyncRabbitMQConsumer(dispatcher=dispatcher)
    sync_service = get_storage_sync_service()
    sync_callback = get_storage_sync_callback()

    tasks = [consumer.run()]
    if sync_service is not None:
        logger.info(
            "Enabling StorageRetrySyncService background worker (interval: %ds, max_retries: %d)",
            settings.STORAGE_SYNC_INTERVAL_SECONDS,
            settings.STORAGE_SYNC_MAX_RETRIES,
        )
        tasks.append(
            sync_service.run_periodic_sync(
                interval_seconds=settings.STORAGE_SYNC_INTERVAL_SECONDS,
                on_synced_callback=sync_callback,
            )
        )

    logger.info("Starting unified background worker...")
    await asyncio.gather(*tasks)


def main() -> None:
    try:
        asyncio.run(run_worker())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Worker stopped by user.")


if __name__ == "__main__":
    main()
