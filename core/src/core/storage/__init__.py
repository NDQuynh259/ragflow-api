"""Object storage ports and adapters."""

from __future__ import annotations

from core.storage.local import LocalStorageAdapter
from core.storage.port import ObjectStoragePort

__all__ = [
    "LocalStorageAdapter",
    "ObjectStoragePort",
]
