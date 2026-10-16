"""Storage ports for persisting intermediate pipeline artifacts.

The Zero-RAM-Bloat strategy (see docs/chunking_implementation_report.md,
section 5) stages parser output such as ``{document_id}_layout.json`` to
object storage instead of keeping it in worker memory.  Storage backends
implement :class:`ObjectStoragePort` so the pipeline can write layout
snapshots, re-chunk later from them, and release RAM eagerly
(``elements.clear()`` + ``gc.collect()``).
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod


class ObjectStoragePort(ABC):
    """Abstract port for storing and retrieving binary pipeline artifacts."""

    @abstractmethod
    def save(self, filename: str, content: bytes, workspace_id: uuid.UUID) -> str:
        """Store content under the workspace and return a storage URI."""
        ...

    @abstractmethod
    def get(self, storage_uri: str) -> bytes:
        """Retrieve stored bytes. Raise if the object is missing."""
        ...

    @abstractmethod
    def delete(self, storage_uri: str) -> bool:
        """Delete stored file. Return True when an object was removed."""
        ...

    def exists(self, storage_uri: str) -> bool:
        """Check whether an object exists at ``storage_uri``."""
        try:
            self.get(storage_uri)
            return True
        except Exception:
            return False

    def get_size(self, storage_uri: str) -> int:
        """Return size in bytes of the object at ``storage_uri``."""
        return len(self.get(storage_uri))


__all__ = ["ObjectStoragePort"]
