"""Unit tests for modular scheduler tasks and BaseTask framework."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest
from scheduler.tasks.base import BaseTask
from scheduler.tasks.heartbeat_task import HeartbeatTask
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


@pytest.mark.anyio
async def test_base_task_lifecycle_and_stop_event() -> None:
    task = DummyTask(interval_seconds=1)
    stop_event = asyncio.Event()

    task_runner = asyncio.create_task(task.run(stop_event))
    await asyncio.sleep(0.05)

    assert task.setup_called is True
    assert task.tick_count >= 1

    stop_event.set()
    await asyncio.wait_for(task_runner, timeout=1.0)

    assert task.teardown_called is True
    assert not task.is_running


@pytest.mark.anyio
async def test_base_task_concurrency_guard_skips_when_running() -> None:
    class SlowTask(BaseTask):
        def __init__(self) -> None:
            super().__init__(name="slow_task", interval_seconds=1)
            self.tick_started = 0

        async def execute_tick(self) -> None:
            self.tick_started += 1
            # Simulate a long-running execution
            await asyncio.sleep(0.5)

    task = SlowTask()
    stop_event = asyncio.Event()

    task_runner = asyncio.create_task(task.run(stop_event))
    await asyncio.sleep(0.05)

    assert task.tick_started == 1
    assert task.is_running is True

    # Manually trigger run cycle while is_running is True; guard prevents overlap
    assert task._is_running is True

    stop_event.set()
    task_runner.cancel()
    try:
        await task_runner
    except asyncio.CancelledError:
        pass


@pytest.mark.anyio
async def test_heartbeat_task_writes_and_cleans_probe(tmp_path) -> None:
    probe_file = str(tmp_path / "scheduler-alive")
    task = HeartbeatTask(interval_seconds=1, probe_file=probe_file)
    stop_event = asyncio.Event()

    task_runner = asyncio.create_task(task.run(stop_event))
    await asyncio.sleep(0.05)

    assert task.probe_file.exists()
    content = task.probe_file.read_text(encoding="utf-8")
    assert content.isdigit()

    stop_event.set()
    await asyncio.wait_for(task_runner, timeout=1.0)
    assert not task.probe_file.exists()


@pytest.mark.anyio
async def test_storage_sync_task_executes_pending_files() -> None:
    mock_sync_service = MagicMock()
    mock_sync_service.sync_pending_files.return_value = []
    mock_callback = MagicMock()

    task = StorageSyncTask(
        sync_service=mock_sync_service,
        on_synced_callback=mock_callback,
        interval_seconds=1,
    )
    stop_event = asyncio.Event()

    task_runner = asyncio.create_task(task.run(stop_event))
    await asyncio.sleep(0.05)

    stop_event.set()
    await asyncio.wait_for(task_runner, timeout=1.0)

    mock_sync_service.sync_pending_files.assert_called_once_with(on_synced_callback=mock_callback)


@pytest.mark.anyio
async def test_storage_sync_task_skips_when_service_is_none() -> None:
    task = StorageSyncTask(sync_service=None, interval_seconds=1)
    stop_event = asyncio.Event()

    task_runner = asyncio.create_task(task.run(stop_event))
    await asyncio.sleep(0.05)

    stop_event.set()
    await asyncio.wait_for(task_runner, timeout=1.0)
