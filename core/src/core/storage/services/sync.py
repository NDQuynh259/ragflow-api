"""Background retry and synchronization service for fallback storage."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.storage.adapters.fallback import FallbackStorageAdapter

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SyncResult:
    """Outcome of attempting to synchronize a local fallback file to primary storage."""

    local_uri: str
    s3_uri: str | None
    success: bool
    error: str | None = None


class StorageRetrySyncService:
    """Periodically scans outbox manifest and retries uploading local fallback files to primary S3 storage."""

    def __init__(
        self,
        fallback_adapter: FallbackStorageAdapter,
        max_retries: int = 10,
    ) -> None:
        self.fallback_adapter = fallback_adapter
        self.max_retries = max_retries

    def sync_pending_files(
        self,
        on_synced_callback: Callable[[str, str, uuid.UUID], None] | None = None,
    ) -> list[SyncResult]:
        """Scan outbox and attempt re-upload of all pending local files to primary S3 storage."""
        pending_items = self.fallback_adapter.get_pending_sync_items()
        if not pending_items:
            return []

        logger.info("Found %d pending storage outbox file(s) to retry sync.", len(pending_items))
        results: list[SyncResult] = []

        for item in pending_items:
            if item.retry_count >= self.max_retries:
                logger.error(
                    "Outbox file %s exceeded max retries (%d). Skipping automatic retry.",
                    item.local_uri,
                    self.max_retries,
                )
                results.append(
                    SyncResult(
                        local_uri=item.local_uri,
                        s3_uri=None,
                        success=False,
                        error=f"Exceeded max retries ({self.max_retries})",
                    )
                )
                continue

            # Verify local file still exists
            if not self.fallback_adapter.secondary.exists(item.local_uri):
                logger.warning(
                    "Local file for outbox item %s no longer exists. Pruning manifest.",
                    item.local_uri,
                )
                self.fallback_adapter.mark_synced(item.local_uri)
                continue

            try:
                # 1. Read raw bytes from local secondary storage
                content = self.fallback_adapter.secondary.get(item.local_uri)

                # 2. Upload to primary S3 storage
                s3_uri = self.fallback_adapter.primary.save(
                    filename=item.filename,
                    content=content,
                    workspace_id=item.workspace_id,
                )
                logger.info(
                    "Successfully retried and uploaded '%s' to primary storage: %s",
                    item.filename,
                    s3_uri,
                )

                # 3. Trigger callback (e.g. update database record)
                if on_synced_callback is not None:
                    on_synced_callback(item.local_uri, s3_uri, item.workspace_id)

                # 4. Cleanup local file and outbox manifest
                self.fallback_adapter.secondary.delete(item.local_uri)
                self.fallback_adapter.mark_synced(item.local_uri)

                results.append(
                    SyncResult(
                        local_uri=item.local_uri,
                        s3_uri=s3_uri,
                        success=True,
                    )
                )

            except Exception as exc:
                item.retry_count += 1
                item.last_error = str(exc)
                self.fallback_adapter.update_outbox_item(item)
                logger.warning(
                    "Retry sync failed for '%s' (Attempt %d/%d): %s",
                    item.filename,
                    item.retry_count,
                    self.max_retries,
                    exc,
                )
                results.append(
                    SyncResult(
                        local_uri=item.local_uri,
                        s3_uri=None,
                        success=False,
                        error=str(exc),
                    )
                )

        return results

    async def run_periodic_sync(
        self,
        interval_seconds: int = 60,
        on_synced_callback: Callable[[str, str, uuid.UUID], None] | None = None,
    ) -> None:
        """Indefinitely runs periodic background sync loop without blocking the main event loop."""
        logger.info(
            "Starting StorageRetrySyncService background worker (interval: %ds, max_retries: %d)",
            interval_seconds,
            self.max_retries,
        )
        while True:
            try:
                self.sync_pending_files(on_synced_callback=on_synced_callback)
            except Exception as exc:
                logger.error("Unexpected error in storage sync cycle: %s", exc, exc_info=True)

            try:
                await asyncio.sleep(interval_seconds)
            except asyncio.CancelledError:
                logger.info("StorageRetrySyncService background worker received shutdown signal.")
                break


__all__ = ["StorageRetrySyncService", "SyncResult"]
