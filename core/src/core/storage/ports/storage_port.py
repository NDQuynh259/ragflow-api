"""Object Storage Port interface."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod


class ObjectStoragePort(ABC):
    """Abstract port for file object storage."""

    @abstractmethod
    def save(self, filename: str, content: bytes, workspace_id: uuid.UUID) -> str:
        """Store content and return storage URI."""
        pass

    @abstractmethod
    def get(self, storage_uri: str) -> bytes:
        """Retrieve stored bytes."""
        pass

    @abstractmethod
    def delete(self, storage_uri: str) -> bool:
        """Delete stored file."""
        pass

    def exists(self, storage_uri: str) -> bool:
        """Check whether file exists at storage URI. Default implementation probes get()."""
        try:
            self.get(storage_uri)
            return True
        except Exception:
            return False

    def get_size(self, storage_uri: str) -> int:
        """Return size in bytes of file at storage URI. Default implementation measures get()."""
        return len(self.get(storage_uri))


__all__ = ["ObjectStoragePort"]
