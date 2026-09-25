"""Periodic task to synchronize local fallback files to primary S3 storage."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING

from scheduler.tasks.base import BaseTask

if TYPE_CHECKING:
    from core.storage import StorageRetrySyncService

logger = logging.getLogger("scheduler.tasks.storage_sync")


class StorageSyncTask(BaseTask):
    """Periodically scans outbox manifest and retries uploading local fallback files to S3."""

    def __init__(
        self,
        sync_service: StorageRetrySyncService | None,
        on_synced_callback: Callable[[str, str, uuid.UUID], None] | None = None,
        interval_seconds: int = 60,
    ) -> None:
        super().__init__(name="storage_retry_sync", interval_seconds=interval_seconds)
        self.sync_service = sync_service
        self.on_synced_callback = on_synced_callback

    async def execute_tick(self) -> None:
        """Scan outbox and retry pending files."""
        if self.sync_service is None:
            logger.debug(
                "No StorageRetrySyncService configured (storage is not FallbackStorageAdapter). Skipping tick."
            )
            return

        try:
            results = self.sync_service.sync_pending_files(
                on_synced_callback=self.on_synced_callback
            )
            if results:
                succeeded = sum(1 for r in results if r.success)
                failed = len(results) - succeeded
                logger.info(
                    "StorageSyncTask tick completed: %d synced, %d failed.",
                    succeeded,
                    failed,
                )
        except Exception as exc:
            logger.error("Unexpected error during storage sync tick: %s", exc, exc_info=True)


__all__ = ["StorageSyncTask"]
