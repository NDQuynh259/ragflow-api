"""Heartbeat and liveness probe task for the scheduler process (inspired by ViShop)."""

from __future__ import annotations

import logging
import os
import sys
import tempfile
import time
from pathlib import Path

from scheduler.tasks.base import BaseTask

logger = logging.getLogger("scheduler.tasks.heartbeat")

DEFAULT_PROBE_FILE = (
    "/tmp/scheduler-alive"
    if sys.platform != "win32"
    else str(Path(tempfile.gettempdir()) / "scheduler-alive")
)


class HeartbeatTask(BaseTask):
    """Refreshes a liveness probe file periodically for container healthchecks."""

    def __init__(
        self,
        interval_seconds: int = 15,
        probe_file: str | None = None,
    ) -> None:
        super().__init__(name="heartbeat_liveness", interval_seconds=interval_seconds)
        self.probe_file = Path(probe_file or os.getenv("SCHEDULER_PROBE_FILE", DEFAULT_PROBE_FILE))

    async def setup(self) -> None:
        """Ensure probe directory exists on startup and write initial heartbeat."""
        self._write_probe()

    async def execute_tick(self) -> None:
        """Write current timestamp to probe file."""
        self._write_probe()

    def _write_probe(self) -> None:
        try:
            self.probe_file.parent.mkdir(parents=True, exist_ok=True)
            self.probe_file.write_text(str(int(time.time())), encoding="utf-8")
        except Exception as exc:
            logger.warning(
                "Failed to refresh scheduler health probe at %s: %s", self.probe_file, exc
            )

    async def teardown(self) -> None:
        """Clean up probe file on graceful shutdown."""
        try:
            if self.probe_file.exists():
                self.probe_file.unlink(missing_ok=True)
        except Exception as exc:
            logger.debug("Could not remove probe file on shutdown: %s", exc)


__all__ = ["DEFAULT_PROBE_FILE", "HeartbeatTask"]
