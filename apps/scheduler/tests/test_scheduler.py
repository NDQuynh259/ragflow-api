"""Unit tests for the dedicated scheduler application."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
from scheduler.main import main, run_scheduler
from scheduler.tasks.base import BaseTask


class FakeTask(BaseTask):
    def __init__(self, name: str = "fake") -> None:
        super().__init__(name=name, interval_seconds=1)
        self.tick_count = 0

    async def execute_tick(self) -> None:
        self.tick_count += 1


@pytest.mark.anyio
async def test_scheduler_runs_registered_tasks_and_terminates() -> None:
    fake_task = FakeTask(name="mock_task")
    stop_event = asyncio.Event()

    with (
        patch("scheduler.main.setup_logging"),
        patch("scheduler.main.get_scheduler_tasks", return_value=[fake_task]),
    ):
        scheduler_task = asyncio.create_task(run_scheduler(stop_event=stop_event))

        await asyncio.sleep(0.05)
        assert not scheduler_task.done()
        assert fake_task.tick_count >= 1

        stop_event.set()
        await asyncio.wait_for(scheduler_task, timeout=1.0)
        assert scheduler_task.done()


@pytest.mark.anyio
async def test_scheduler_empty_tasks_waits_for_stop_event() -> None:
    stop_event = asyncio.Event()

    with (
        patch("scheduler.main.setup_logging"),
        patch("scheduler.main.get_scheduler_tasks", return_value=[]),
    ):
        scheduler_task = asyncio.create_task(run_scheduler(stop_event=stop_event))

        await asyncio.sleep(0.05)
        assert not scheduler_task.done()

        stop_event.set()
        await asyncio.wait_for(scheduler_task, timeout=1.0)
        assert scheduler_task.done()


def test_scheduler_main_handles_keyboard_interrupt() -> None:
    with (
        patch("scheduler.main.run_scheduler", side_effect=KeyboardInterrupt),
        patch("scheduler.main.asyncio.run", side_effect=KeyboardInterrupt),
    ):
        main()
