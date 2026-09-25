"""Modular scheduled tasks for the scheduler application."""

from __future__ import annotations

from scheduler.tasks.base import BaseTask
from scheduler.tasks.heartbeat_task import DEFAULT_PROBE_FILE, HeartbeatTask
from scheduler.tasks.monthly_cleanup_task import MonthlyStorageCleanupTask
from scheduler.tasks.storage_sync_task import StorageSyncTask

__all__ = [
    "DEFAULT_PROBE_FILE",
    "BaseTask",
    "HeartbeatTask",
    "MonthlyStorageCleanupTask",
    "StorageSyncTask",
]
