"""Storage Adapters for Local filesystem, MinIO S3, and Fallback."""

from __future__ import annotations

from core.storage.adapters.fallback import FallbackStorageAdapter, OutboxItem
from core.storage.adapters.local import LocalStorageAdapter
from core.storage.adapters.minio import MinioStorageAdapter

__all__ = [
    "FallbackStorageAdapter",
    "LocalStorageAdapter",
    "MinioStorageAdapter",
    "OutboxItem",
]
