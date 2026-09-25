"""Unit tests for modular scheduler tasks and BaseTask framework."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from scheduler.tasks.base import BaseTask
from scheduler.tasks.heartbeat_task import HeartbeatTask
from scheduler.tasks.monthly_cleanup_task import MonthlyStorageCleanupTask
from scheduler.tasks.storage_sync_task import StorageSyncTask


class DummyTask(BaseTask):
    def __init__(self, interval_seconds: int = 1) -> None:
        super().__init__(name="dummy_task", interval_seconds=interval_seconds)
        self.tick_count = 0
        self.setup_called = False
        self.teardown_called = False

    async def setup(self) -> None:
        self.setup_called = True

    async def teardown(self) -> None:
        self.teardown_called = True

    async def execute_tick(self) -> None:
        self.tick_count += 1


def test_base_task_triggers() -> None:
    interval_task = DummyTask(interval_seconds=60)
    assert isinstance(interval_task.get_trigger(), IntervalTrigger)

    cron_task = MonthlyStorageCleanupTask(cron_expression="30 4 1 * *")
    assert isinstance(cron_task.get_trigger(), CronTrigger)

    class IncompleteTask(BaseTask):
        async def execute_tick(self) -> None:
            pass

    with pytest.raises(ValueError, match="must have either interval_seconds or cron_expression"):
        IncompleteTask(name="invalid_task")


@pytest.mark.anyio
async def test_base_task_safe_execute_tick_and_concurrency_guard() -> None:
    task = DummyTask(interval_seconds=1)
    await task.setup()
    assert task.setup_called is True

    await task.safe_execute_tick()
    assert task.tick_count == 1
    assert not task.is_running

    # Test concurrency guard
    task._is_running = True
    await task.safe_execute_tick()
    # tick_count should not increase because it was skipped
    assert task.tick_count == 1

    task._is_running = False
    await task.teardown()
    assert task.teardown_called is True


@pytest.mark.anyio
async def test_heartbeat_task_writes_and_cleans_probe(tmp_path) -> None:
    probe_file = str(tmp_path / "scheduler-alive")
    task = HeartbeatTask(interval_seconds=1, probe_file=probe_file)

    await task.setup()
    assert task.probe_file.exists()
    content = task.probe_file.read_text(encoding="utf-8")
    assert content.isdigit()

    await task.execute_tick()
    assert task.probe_file.exists()

    await task.teardown()
    assert not task.probe_file.exists()


@pytest.mark.anyio
async def test_storage_sync_task_executes_pending_files() -> None:
    mock_sync_service = MagicMock()
    mock_sync_service.sync_pending_files.return_value = []
    mock_callback = MagicMock()

    task = StorageSyncTask(
        sync_service=mock_sync_service,
        on_synced_callback=mock_callback,
        interval_seconds=60,
    )

    await task.execute_tick()
    mock_sync_service.sync_pending_files.assert_called_once_with(on_synced_callback=mock_callback)


@pytest.mark.anyio
async def test_storage_sync_task_skips_when_service_is_none() -> None:
    task = StorageSyncTask(sync_service=None, interval_seconds=60)
    await task.execute_tick()  # Should not raise exception


@pytest.mark.anyio
async def test_monthly_cleanup_task_cleans_stale_temp_files(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("core.config.settings.STORAGE_DIR", str(tmp_path))

    temp_dir = tmp_path / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    # 1 stale file (modified 35 days ago)
    stale_file = temp_dir / "old_upload.tmp"
    stale_file.write_text("old data")
    old_time = time.time() - (35 * 86400)
    import os

    os.utime(stale_file, (old_time, old_time))

    # 1 recent file (modified today)
    recent_file = temp_dir / "recent_upload.tmp"
    recent_file.write_text("recent data")

    task = MonthlyStorageCleanupTask(retention_days=30)
    assert isinstance(task.get_trigger(), CronTrigger)

    await task.execute_tick()

    assert not stale_file.exists()
    assert recent_file.exists()
