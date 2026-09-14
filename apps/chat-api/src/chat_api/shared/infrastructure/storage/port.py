"""Object Storage Port interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
import uuid


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
