"""Object storage ports, adapters, and file upload services.

Organized into:
- ports: Abstract interfaces defining storage contracts
- adapters: Concrete implementations (Local, MinIO, Fallback)
- services: Validation, file upload coordination, retry sync, and factory wiring
"""

from __future__ import annotations

from core.storage.adapters import (
    FallbackStorageAdapter,
    LocalStorageAdapter,
    MinioStorageAdapter,
    OutboxItem,
)
from core.storage.ports import ObjectStoragePort
from core.storage.services import (
    DEFAULT_ALLOWED_EXTENSIONS,
    DEFAULT_MAX_FILE_SIZE_BYTES,
    EXTENSION_MIME_MAP,
    FileUploader,
    FileValidator,
    StorageRetrySyncService,
    SyncResult,
    UploadResult,
    ValidatedFile,
    create_storage_adapter,
    create_storage_sync_service,
)

__all__ = [
    "DEFAULT_ALLOWED_EXTENSIONS",
    "DEFAULT_MAX_FILE_SIZE_BYTES",
    "EXTENSION_MIME_MAP",
    "FallbackStorageAdapter",
    "FileUploader",
    "FileValidator",
    "LocalStorageAdapter",
    "MinioStorageAdapter",
    "ObjectStoragePort",
    "OutboxItem",
    "StorageRetrySyncService",
    "SyncResult",
    "UploadResult",
    "ValidatedFile",
    "create_storage_adapter",
    "create_storage_sync_service",
]
