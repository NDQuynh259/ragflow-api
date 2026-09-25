"""Dedicated Background Scheduler Process for periodic tasks and retry synchronization."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from core.logging import setup_logging
from scheduler.dependencies import get_scheduler_tasks

logger = logging.getLogger("scheduler")


async def run_scheduler(stop_event: asyncio.Event | None = None) -> None:
    """Run all scheduled recurring jobs in a dedicated single-instance process using APScheduler."""
    setup_logging()
    logger.info("Initializing dedicated APScheduler process...")

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

    # Call setup on each task
    for task in registered_tasks:
        try:
            await task.setup()
        except Exception as exc:
            logger.error("Error setting up task '%s': %s", task.name, exc, exc_info=True)

    scheduler = AsyncIOScheduler(timezone="UTC")

    for task in registered_tasks:
        trigger = task.get_trigger()
        scheduler.add_job(
            task.safe_execute_tick,
            trigger=trigger,
            id=task.name,
            name=task.name,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=60,
        )
        logger.info("Registered job '%s' with trigger: %s", task.name, trigger)

    scheduler.start()
    logger.info(
        "Dedicated APScheduler running with %d registered job(s).",
        len(registered_tasks),
    )

    try:
        await stop_event.wait()
    finally:
        logger.info("Shutting down APScheduler...")
        scheduler.shutdown(wait=False)
        for task in registered_tasks:
            try:
                await task.teardown()
            except Exception as exc:
                logger.error("Error tearing down task '%s': %s", task.name, exc, exc_info=True)
        logger.info("Dedicated APScheduler shutdown complete.")


def main() -> None:
    """CLI Entrypoint for scheduler."""
    try:
        asyncio.run(run_scheduler())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler process stopped.")


if __name__ == "__main__":
    main()
