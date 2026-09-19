"""Server-Sent Events (SSE) formatting utilities adhering to W3C specification."""

from __future__ import annotations

import json
from typing import Any


def format_sse(
    event: str | None = None,
    data: Any = None,
    event_id: str | None = None,
    retry: int | None = None,
) -> str:
    """Format fields into standard W3C Server-Sent Events (SSE) text block.

    Reference: https://html.spec.whatwg.org/multipage/server-sent-events.html
    """
    lines: list[str] = []

    if event_id is not None:
        lines.append(f"id: {event_id}")

    if event:
        lines.append(f"event: {event}")

    if retry is not None:
        lines.append(f"retry: {retry}")

    if data is not None:
        if isinstance(data, (dict, list)):
            payload_str = json.dumps(data, ensure_ascii=False)
        else:
            payload_str = str(data)

        for line in payload_str.splitlines():
            lines.append(f"data: {line}")
    else:
        lines.append("data: ")

    lines.append("")
    lines.append("")
    return "\n".join(lines)


def format_ping(comment: str = "ping") -> str:
    """Format an SSE comment line used for keep-alive heartbeats."""
    return f": {comment}\n\n"


__all__ = ["format_sse", "format_ping"]
