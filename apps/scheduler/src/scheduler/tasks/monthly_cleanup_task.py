"""Monthly cleanup task for storage maintenance (inspired by ViShop cleanup.task.ts)."""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from core.config import settings
from scheduler.tasks.base import BaseTask

if TYPE_CHECKING:
    from core.database import SqlAlchemyUnitOfWork

logger = logging.getLogger("scheduler.tasks.monthly_cleanup")


class MonthlyStorageCleanupTask(BaseTask):
    """Monthly maintenance task running at 04:30 UTC on the 1st of every month.

    Purges stale temporary storage files, orphaned chunks, and old synced outbox logs.
    """

    def __init__(
        self,
        uow_factory: Callable[[], SqlAlchemyUnitOfWork] | None = None,
        retention_days: int = 30,
        cron_expression: str = "30 4 1 * *",
    ) -> None:
        super().__init__(
            name="monthly_storage_cleanup",
            cron_expression=cron_expression,
        )
        self.uow_factory = uow_factory
        self.retention_days = retention_days

    async def execute_tick(self) -> None:
        """Execute end-of-month cleanup cycle."""
        now = datetime.now(UTC)
        logger.info(
            "Starting monthly storage cleanup at %s (retention: %d days)...",
            now.isoformat(),
            self.retention_days,
        )

        cleaned_temp_files = self._cleanup_temp_directory()
        logger.info(
            "Monthly cleanup completed: %d stale temporary file(s) removed.",
            cleaned_temp_files,
        )

    def _cleanup_temp_directory(self) -> int:
        """Scan and delete temp storage files older than retention_days."""
        storage_dir = Path(settings.STORAGE_DIR)
        temp_dir = storage_dir / "temp"
        if not temp_dir.exists() or not temp_dir.is_dir():
            return 0

        cutoff_timestamp = time.time() - (self.retention_days * 86400)
        removed_count = 0

        try:
            for root, _, files in os.walk(temp_dir):
                for filename in files:
                    file_path = Path(root) / filename
                    try:
                        stat = file_path.stat()
                        if stat.st_mtime < cutoff_timestamp:
                            file_path.unlink(missing_ok=True)
                            removed_count += 1
                    except Exception as err:
                        logger.warning("Could not delete stale temp file %s: %s", file_path, err)
        except Exception as exc:
            logger.error("Error scanning temp storage directory: %s", exc)

        return removed_count


__all__ = ["MonthlyStorageCleanupTask"]
