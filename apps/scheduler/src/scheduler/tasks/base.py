"""Base class for all scheduled tasks in the scheduler application."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from apscheduler.triggers.base import BaseTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger("scheduler.tasks")


class BaseTask(ABC):
    """Abstract base task providing lifecycle management, trigger resolution, and execution guard."""

    def __init__(
        self,
        name: str,
        interval_seconds: int | None = None,
        cron_expression: str | None = None,
    ) -> None:
        if interval_seconds is None and cron_expression is None:
            raise ValueError(
                f"Task '{name}' must have either interval_seconds or cron_expression defined."
            )
        if interval_seconds is not None and interval_seconds <= 0:
            raise ValueError(f"Task interval_seconds must be positive, got {interval_seconds}")

        self.name = name
        self.interval_seconds = interval_seconds
        self.cron_expression = cron_expression
        self._is_running = False

    @property
    def is_running(self) -> bool:
        """Return whether a tick execution is currently in progress."""
        return self._is_running

    def get_trigger(self) -> BaseTrigger:
        """Resolve and return an APScheduler trigger (CronTrigger or IntervalTrigger)."""
        if self.cron_expression is not None:
            return CronTrigger.from_crontab(self.cron_expression, timezone="UTC")
        if self.interval_seconds is not None:
            return IntervalTrigger(seconds=self.interval_seconds, timezone="UTC")
        raise ValueError(f"Task '{self.name}' has no valid trigger configuration.")

    async def setup(self) -> None:
        """Optional lifecycle hook called once before the scheduler starts."""
        pass

    async def teardown(self) -> None:
        """Optional lifecycle hook called once after the scheduler shuts down."""
        pass

    @abstractmethod
    async def execute_tick(self) -> None:
        """Execute one cycle of the scheduled task. Must be implemented by subclasses."""
        ...

    async def safe_execute_tick(self) -> None:
        """Execution wrapper invoked by APScheduler, equipped with defensive Concurrency Guard."""
        if self._is_running:
            logger.debug(
                "Task '%s' is already running from previous execution. Skipping tick.",
                self.name,
            )
            return

        self._is_running = True
        try:
            await self.execute_tick()
        except Exception as exc:
            logger.error("Unhandled error in task '%s': %s", self.name, exc, exc_info=True)
        finally:
            self._is_running = False


__all__ = ["BaseTask"]
