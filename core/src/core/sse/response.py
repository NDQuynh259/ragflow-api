"""FastAPI/Starlette SSEResponse configured with standard SSE headers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from starlette.responses import StreamingResponse

from core.sse.message import SSEMessage


async def _wrap_sse_content(
    content: AsyncIterator[str | SSEMessage],
) -> AsyncIterator[str]:
    """Ensure any SSEMessage items are encoded to W3C SSE text."""
    async for item in content:
        if isinstance(item, SSEMessage):
            yield item.encode()
        else:
            yield item


class SSEResponse(StreamingResponse):
    """Production-grade Server-Sent Events response with essential proxy headers."""

    DEFAULT_SSE_HEADERS: dict[str, str] = {
        "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-cache, no-transform",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",  # Disables Nginx response buffering for instant streaming
    }

    def __init__(
        self,
        content: AsyncIterator[str | SSEMessage],
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        background: Any = None,
    ) -> None:
        merged_headers = dict(self.DEFAULT_SSE_HEADERS)
        if headers:
            merged_headers.update(headers)

        super().__init__(
            content=_wrap_sse_content(content),
            status_code=status_code,
            headers=merged_headers,
            media_type="text/event-stream",
            background=background,
        )


__all__ = ["SSEResponse"]
