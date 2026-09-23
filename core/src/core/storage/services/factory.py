"""Storage adapter factory based on system configuration."""

from __future__ import annotations

from core.config import CoreSettings, settings as default_settings
from core.storage.adapters.minio import MinioStorageAdapter
from core.storage.ports.storage_port import ObjectStoragePort


def create_storage_adapter(cfg: CoreSettings | None = None) -> ObjectStoragePort:
    """Instantiate the configured storage adapter (MinIO / S3)."""
    conf = cfg or default_settings

    return MinioStorageAdapter(
        endpoint=conf.MINIO_ENDPOINT,
        access_key=conf.MINIO_ACCESS_KEY,
        secret_key=conf.MINIO_SECRET_KEY,
        bucket_name=conf.MINIO_BUCKET_NAME,
        secure=conf.MINIO_SECURE,
        region=conf.MINIO_REGION,
    )


__all__ = ["create_storage_adapter"]
