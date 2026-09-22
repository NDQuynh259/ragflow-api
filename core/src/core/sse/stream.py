"""Asynchronous SSE stream generator with automatic heartbeat ping."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from core.sse.message import SSEMessage, ping_message

logger = logging.getLogger(__name__)


async def sse_event_stream(
    queue: asyncio.Queue[SSEMessage],
    ping_interval: float = 15.0,
) -> AsyncIterator[str]:
    """Consume SSEMessages from queue and yield encoded text with periodic pings.

    Args:
        queue: Asynchronous queue where incoming SSE messages are placed.
        ping_interval: Seconds to wait before emitting a keep-alive ping comment.
    """
    try:
        while True:
            try:
                message = await asyncio.wait_for(queue.get(), timeout=ping_interval)
                yield message.encode()
                queue.task_done()
            except TimeoutError:
                # Emit keep-alive comment so proxy / browser connection stays active
                yield ping_message().encode()

    except asyncio.CancelledError:
        logger.debug("SSE stream consumer disconnected or cancelled.")
        raise


__all__ = ["sse_event_stream"]
