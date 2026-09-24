"""Dedicated Background Scheduler Process for periodic tasks and retry synchronization.

Separated from the Ingestion Worker to:
1. Prevent race conditions and duplicate outbox scans when Ingestion Workers are scaled out.
2. Isolate lightweight cron/sync tasks from heavy OCR/Docling processing and potential worker OOMs.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

from core.config import settings
from core.logging import setup_logging
from worker.dependencies import get_storage_sync_callback, get_storage_sync_service

logger = logging.getLogger("worker.scheduler")


async def run_scheduler(stop_event: asyncio.Event | None = None) -> None:
    """Run all scheduled recurring jobs in a dedicated single-instance process."""
    setup_logging()
    logger.info("Initializing dedicated Scheduler process...")

    if stop_event is None:
        stop_event = asyncio.Event()

    # Setup signal handlers for graceful shutdown on Linux/Docker
    if sys.platform != "win32":
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop_event.set)

    sync_service = get_storage_sync_service()
    sync_callback = get_storage_sync_callback()

    tasks: list[asyncio.Task] = []

    if sync_service is not None:
        logger.info(
            "Registered StorageRetrySyncService (interval: %ds, max_retries: %d)",
            settings.STORAGE_SYNC_INTERVAL_SECONDS,
            settings.STORAGE_SYNC_MAX_RETRIES,
        )
        sync_task = asyncio.create_task(
            sync_service.run_periodic_sync(
                interval_seconds=settings.STORAGE_SYNC_INTERVAL_SECONDS,
                on_synced_callback=sync_callback,
                stop_event=stop_event,
            ),
            name="storage_retry_sync",
        )
        tasks.append(sync_task)
    else:
        logger.warning(
            "No StorageRetrySyncService configured (storage is not configured with fallback outbox)."
        )

    if not tasks:
        logger.info("No active scheduled tasks to run. Scheduler waiting for stop event...")
        await stop_event.wait()
        return

    logger.info("Dedicated Scheduler running with %d registered background task(s).", len(tasks))

    # Await until stop_event is set or any task completes/errors
    stop_waiter = asyncio.create_task(stop_event.wait(), name="scheduler_stop_waiter")
    try:
        done, _ = await asyncio.wait(
            [stop_waiter, *tasks],
            return_when=asyncio.FIRST_COMPLETED,
        )
    finally:
        stop_event.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        if not stop_waiter.done():
            stop_waiter.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("Dedicated Scheduler shutdown complete.")


def main() -> None:
    """CLI Entrypoint for worker.scheduler."""
    try:
        asyncio.run(run_scheduler())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler process stopped.")


if __name__ == "__main__":
    main()
