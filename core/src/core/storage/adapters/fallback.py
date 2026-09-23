"""Resilient Fallback Storage Adapter with primary S3/MinIO and secondary local storage."""

from __future__ import annotations

import logging
import uuid

from core.storage.ports.storage_port import ObjectStoragePort

logger = logging.getLogger(__name__)


class FallbackStorageAdapter(ObjectStoragePort):
    """Storage adapter that attempts primary storage first (e.g. MinIO/S3),

    and automatically falls back to secondary storage (e.g. local server) if primary fails.
    """

    def __init__(
        self,
        primary: ObjectStoragePort,
        secondary: ObjectStoragePort,
    ) -> None:
        self.primary = primary
        self.secondary = secondary

    def save(self, filename: str, content: bytes, workspace_id: uuid.UUID) -> str:
        """Attempt primary upload first. If error occurs, fall back immediately to secondary."""
        try:
            uri = self.primary.save(filename, content, workspace_id)
            logger.info("Successfully saved '%s' to primary storage: %s", filename, uri)
            return uri
        except Exception as exc:
            logger.warning(
                "Primary storage failed to save '%s' (Error: %s). Falling back to secondary local storage.",
                filename,
                exc,
            )
            fallback_uri = self.secondary.save(filename, content, workspace_id)
            logger.info("Fallback saved '%s' to local server storage: %s", filename, fallback_uri)
            return fallback_uri

    def get(self, storage_uri: str) -> bytes:
        """Route read request to corresponding adapter based on URI scheme."""
        if storage_uri.startswith(("s3://", "minio://")):
            try:
                return self.primary.get(storage_uri)
            except Exception:
                if self.secondary.exists(storage_uri):
                    return self.secondary.get(storage_uri)
                raise
        return self.secondary.get(storage_uri)

    def delete(self, storage_uri: str) -> bool:
        """Delete from the appropriate storage provider according to URI scheme."""
        if storage_uri.startswith(("s3://", "minio://")):
            return self.primary.delete(storage_uri)
        return self.secondary.delete(storage_uri)

    def exists(self, storage_uri: str) -> bool:
        """Check presence of object in the corresponding storage provider."""
        if storage_uri.startswith(("s3://", "minio://")):
            return self.primary.exists(storage_uri)
        return self.secondary.exists(storage_uri)

    def get_size(self, storage_uri: str) -> int:
        """Retrieve size of object from corresponding storage provider."""
        if storage_uri.startswith(("s3://", "minio://")):
            return self.primary.get_size(storage_uri)
        return self.secondary.get_size(storage_uri)


__all__ = ["FallbackStorageAdapter"]
