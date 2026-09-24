"""Unit tests for the dedicated background scheduler process."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from worker.scheduler import main, run_scheduler


@pytest.mark.anyio
async def test_scheduler_runs_sync_service_and_terminates_on_stop_event() -> None:
    stop_event = asyncio.Event()

    mock_sync_service = MagicMock()

    async def fake_periodic_sync(interval_seconds, on_synced_callback, stop_event):
        # Wait until stop_event is set
        await stop_event.wait()

    mock_sync_service.run_periodic_sync = AsyncMock(side_effect=fake_periodic_sync)
    mock_callback = MagicMock()

    with (
        patch("worker.scheduler.setup_logging"),
        patch("worker.scheduler.get_storage_sync_service", return_value=mock_sync_service),
        patch("worker.scheduler.get_storage_sync_callback", return_value=mock_callback),
    ):
        scheduler_task = asyncio.create_task(run_scheduler(stop_event=stop_event))

        # Give the event loop a tick to start the background tasks
        await asyncio.sleep(0.05)
        assert not scheduler_task.done()

        # Signal shutdown
        stop_event.set()
        await asyncio.wait_for(scheduler_task, timeout=1.0)

        mock_sync_service.run_periodic_sync.assert_called_once()
        call_kwargs = mock_sync_service.run_periodic_sync.call_args[1]
        assert call_kwargs["on_synced_callback"] == mock_callback
        assert call_kwargs["stop_event"] == stop_event


@pytest.mark.anyio
async def test_scheduler_without_sync_service_waits_cleanly() -> None:
    stop_event = asyncio.Event()

    with (
        patch("worker.scheduler.setup_logging"),
        patch("worker.scheduler.get_storage_sync_service", return_value=None),
        patch("worker.scheduler.get_storage_sync_callback", return_value=None),
    ):
        scheduler_task = asyncio.create_task(run_scheduler(stop_event=stop_event))

        await asyncio.sleep(0.05)
        assert not scheduler_task.done()

        stop_event.set()
        await asyncio.wait_for(scheduler_task, timeout=1.0)
        assert scheduler_task.done()


def test_scheduler_main_handles_keyboard_interrupt() -> None:
    with (
        patch("worker.scheduler.run_scheduler", side_effect=KeyboardInterrupt),
        patch("worker.scheduler.asyncio.run", side_effect=KeyboardInterrupt),
    ):
        # Should not raise exception
        main()


@pytest.mark.anyio
async def test_worker_main_runs_consumer() -> None:
    from worker.main import run_worker

    mock_consumer = MagicMock()
    mock_consumer.run = AsyncMock()

    with (
        patch("worker.main.setup_logging"),
        patch("worker.main.build_dispatcher"),
        patch("worker.main.AsyncRabbitMQConsumer", return_value=mock_consumer),
    ):
        await run_worker()
        mock_consumer.run.assert_called_once()
