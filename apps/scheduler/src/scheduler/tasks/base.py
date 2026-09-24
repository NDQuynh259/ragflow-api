"""Base class for all scheduled tasks in the scheduler application."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger("scheduler.tasks")


class BaseTask(ABC):
    """Abstract base task providing lifecycle management, interval loops, and concurrency protection."""

    def __init__(self, name: str, interval_seconds: int) -> None:
        if interval_seconds <= 0:
            raise ValueError(f"Task interval_seconds must be positive, got {interval_seconds}")
        self.name = name
        self.interval_seconds = interval_seconds
        self._is_running = False

    @property
    def is_running(self) -> bool:
        """Return whether a tick execution is currently in progress."""
        return self._is_running

    async def setup(self) -> None:
        """Optional lifecycle hook called once before the periodic loop starts."""
        pass

    async def teardown(self) -> None:
        """Optional lifecycle hook called once after the periodic loop finishes or is cancelled."""
        pass

    @abstractmethod
    async def execute_tick(self) -> None:
        """Execute one cycle of the scheduled task. Must be implemented by subclasses."""
        ...

    async def run(self, stop_event: asyncio.Event) -> None:
        """Run the task periodically until stop_event is signaled."""
        logger.info("Starting task '%s' (interval: %ds)", self.name, self.interval_seconds)
        try:
            await self.setup()
        except Exception as exc:
            logger.error("Error during setup for task '%s': %s", self.name, exc, exc_info=True)

        while not stop_event.is_set():
            # Concurrency Guard (ViShop Pattern)
            if self._is_running:
                logger.debug(
                    "Task '%s' is still running from previous tick. Skipping this tick.",
                    self.name,
                )
            else:
                self._is_running = True
                try:
                    await self.execute_tick()
                except asyncio.CancelledError:
                    logger.info("Task '%s' received cancellation during execution.", self.name)
                    break
                except Exception as exc:
                    logger.error("Unhandled error in task '%s': %s", self.name, exc, exc_info=True)
                finally:
                    self._is_running = False

            # Sleep until next tick or until stop_event is set
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self.interval_seconds)
                # If stop_event was triggered, break out of loop
                break
            except TimeoutError:
                # Interval elapsed normally, proceed to next tick
                pass
            except asyncio.CancelledError:
                logger.info("Task '%s' received shutdown signal.", self.name)
                break

        logger.info("Stopping task '%s'...", self.name)
        try:
            await self.teardown()
        except Exception as exc:
            logger.error("Error during teardown for task '%s': %s", self.name, exc, exc_info=True)
        logger.info("Task '%s' stopped cleanly.", self.name)


__all__ = ["BaseTask"]
