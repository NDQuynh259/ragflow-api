"""Object storage ports, adapters, and file upload services.

Organized into:
- ports: Abstract interfaces defining storage contracts
- adapters: Concrete implementations (MinIO, Fallback)
- services: Validation, file upload coordination, and factory wiring
"""

from __future__ import annotations

from core.storage.adapters import (
    FallbackStorageAdapter,
    MinioStorageAdapter,
)
from core.storage.ports import ObjectStoragePort
from core.storage.services import (
    DEFAULT_ALLOWED_EXTENSIONS,
    DEFAULT_MAX_FILE_SIZE_BYTES,
    EXTENSION_MIME_MAP,
    FileUploader,
    FileValidator,
    UploadResult,
    ValidatedFile,
    create_storage_adapter,
)

__all__ = [
    "DEFAULT_ALLOWED_EXTENSIONS",
    "DEFAULT_MAX_FILE_SIZE_BYTES",
    "EXTENSION_MIME_MAP",
    "FallbackStorageAdapter",
    "FileUploader",
    "FileValidator",
    "MinioStorageAdapter",
    "ObjectStoragePort",
    "UploadResult",
    "ValidatedFile",
    "create_storage_adapter",
]
