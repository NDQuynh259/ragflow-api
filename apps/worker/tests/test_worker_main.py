"""Unit tests for worker entrypoint."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from worker.main import run_worker


@pytest.mark.anyio
async def test_worker_main_runs_consumer() -> None:
    mock_consumer = MagicMock()
    mock_consumer.run = AsyncMock()

    with (
        patch("worker.main.setup_logging"),
        patch("worker.main.build_dispatcher"),
        patch("worker.main.AsyncRabbitMQConsumer", return_value=mock_consumer),
    ):
        await run_worker()
        mock_consumer.run.assert_called_once()
