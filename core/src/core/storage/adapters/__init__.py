"""Storage Adapters for MinIO and Fallback."""

from __future__ import annotations

from core.storage.adapters.fallback import FallbackStorageAdapter
from core.storage.adapters.minio import MinioStorageAdapter

__all__ = [
    "FallbackStorageAdapter",
    "MinioStorageAdapter",
]
