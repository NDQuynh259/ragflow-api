"""Storage adapter factory based on system configuration."""

from __future__ import annotations

from core.config import CoreSettings, settings as default_settings
from core.storage.adapters.fallback import FallbackStorageAdapter
from core.storage.adapters.local import LocalStorageAdapter
from core.storage.adapters.minio import MinioStorageAdapter
from core.storage.ports.storage_port import ObjectStoragePort
from core.storage.services.sync import StorageRetrySyncService


def create_storage_adapter(cfg: CoreSettings | None = None) -> ObjectStoragePort:
    """Instantiate the configured storage adapter (MinIO, Local, or MinIO with Local Fallback)."""
    conf = cfg or default_settings
    backend = getattr(conf, "STORAGE_BACKEND", "minio_with_local_fallback").lower()

    local_adapter = LocalStorageAdapter(base_dir=conf.STORAGE_DIR)

    if backend == "local":
        return local_adapter

    minio_adapter = MinioStorageAdapter(
        endpoint=conf.MINIO_ENDPOINT,
        access_key=conf.MINIO_ACCESS_KEY,
        secret_key=conf.MINIO_SECRET_KEY,
        bucket_name=conf.MINIO_BUCKET_NAME,
        secure=conf.MINIO_SECURE,
        region=conf.MINIO_REGION,
    )

    if backend == "minio":
        return minio_adapter

    # Default: minio_with_local_fallback
    return FallbackStorageAdapter(
        primary=minio_adapter,
        secondary=local_adapter,
    )


def create_storage_sync_service(
    storage_adapter: ObjectStoragePort,
    cfg: CoreSettings | None = None,
) -> StorageRetrySyncService | None:
    """Create a StorageRetrySyncService if the storage adapter is a FallbackStorageAdapter."""
    if not isinstance(storage_adapter, FallbackStorageAdapter):
        return None

    conf = cfg or default_settings
    max_retries = getattr(conf, "STORAGE_SYNC_MAX_RETRIES", 10)
    return StorageRetrySyncService(
        fallback_adapter=storage_adapter,
        max_retries=max_retries,
    )


__all__ = ["create_storage_adapter", "create_storage_sync_service"]
