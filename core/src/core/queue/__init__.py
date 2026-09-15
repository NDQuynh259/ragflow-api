"""Ingestion queue ports and adapters."""

from __future__ import annotations

from core.queue.background import BackgroundQueueAdapter
from core.queue.port import IngestionQueuePort

__all__ = [
    "BackgroundQueueAdapter",
    "IngestionQueuePort",
]
