"""Dedicated Background Scheduler Process for periodic tasks and retry synchronization.

Separated as an independent application from the Ingestion Worker to:
1. Prevent race conditions and duplicate outbox scans when Ingestion Workers are scaled out.
2. Isolate lightweight cron/sync tasks from heavy OCR/Docling processing and potential worker OOMs.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

from core.logging import setup_logging
from scheduler.dependencies import get_scheduler_tasks

logger = logging.getLogger("scheduler")


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

    registered_tasks = get_scheduler_tasks()
    if not registered_tasks:
        logger.info("No active scheduled tasks to run. Scheduler waiting for stop event...")
        await stop_event.wait()
        return

    logger.info(
        "Dedicated Scheduler running with %d registered background task(s).",
        len(registered_tasks),
    )

    running_tasks: list[asyncio.Task] = [
        asyncio.create_task(task.run(stop_event), name=task.name) for task in registered_tasks
    ]

    # Await until stop_event is set or any task completes/errors
    stop_waiter = asyncio.create_task(stop_event.wait(), name="scheduler_stop_waiter")
    try:
        await asyncio.wait(
            [stop_waiter, *running_tasks],
            return_when=asyncio.FIRST_COMPLETED,
        )
    finally:
        stop_event.set()
        for task in running_tasks:
            if not task.done():
                task.cancel()
        if not stop_waiter.done():
            stop_waiter.cancel()
        await asyncio.gather(*running_tasks, return_exceptions=True)
        logger.info("Dedicated Scheduler shutdown complete.")


def main() -> None:
    """CLI Entrypoint for scheduler."""
    try:
        asyncio.run(run_scheduler())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler process stopped.")


if __name__ == "__main__":
    main()
