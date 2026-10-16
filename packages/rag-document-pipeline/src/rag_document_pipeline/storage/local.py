"""Local filesystem storage adapter for pipeline artifacts.

This adapter is intended for development and tests.  It stores files in a
workspace-specific directory and returns ``file://`` URIs, which makes the
same save/get/delete contract usable with an object-storage adapter in
production.  Layout snapshots can therefore be staged locally while
experimenting with re-chunking without retaining them in memory.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from urllib.parse import unquote, urlparse

from rag_document_pipeline.storage.ports import ObjectStoragePort


class LocalStorageAdapter(ObjectStoragePort):
    """Store pipeline objects below a local base directory.

    ``workspace_id`` is kept in the path to prevent files belonging to one
    workspace from being mixed with another.  Only the basename of
    ``filename`` is used; callers cannot escape the workspace directory with
    ``..`` components.
    """

    def __init__(self, base_dir: str | os.PathLike[str]) -> None:
        if not base_dir:
            raise ValueError("base_dir must not be empty")
        self.base_dir = Path(base_dir).expanduser().resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _workspace_name(workspace_id: uuid.UUID | str) -> str:
        value = str(workspace_id).strip()
        if not value or value in {".", ".."} or "/" in value or "\\" in value:
            raise ValueError("workspace_id must be a non-empty path-safe value")
        return value

    def save(
        self,
        filename: str,
        content: bytes,
        workspace_id: uuid.UUID | str,
    ) -> str:
        """Persist ``content`` and return its ``file://`` URI."""
        if not isinstance(content, bytes):
            raise TypeError("content must be bytes")
        name = Path(filename).name
        if not name or name in {".", ".."}:
            raise ValueError("filename must contain a file name")

        workspace_dir = self.base_dir / self._workspace_name(workspace_id)
        workspace_dir.mkdir(parents=True, exist_ok=True)
        target = workspace_dir / f"{uuid.uuid4().hex[:8]}_{name}"

        # The temporary file plus replace is atomic on the same filesystem
        # and avoids exposing a partially-written layout.json to a
        # concurrent reader.
        temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_bytes(content)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        return target.as_uri()

    @staticmethod
    def _path_from_uri(storage_uri: str) -> Path:
        """Convert a file URI (or a local path) into a filesystem path."""
        if not isinstance(storage_uri, str) or not storage_uri:
            raise ValueError("storage_uri must be a non-empty string")
        parsed = urlparse(storage_uri)
        if parsed.scheme and parsed.scheme != "file":
            raise ValueError(f"unsupported storage URI scheme: {parsed.scheme}")
        if parsed.scheme == "file":
            # ``Path.as_uri`` emits an empty netloc on POSIX and a drive path
            # on Windows.  Reject remote file hosts rather than silently
            # accessing an unexpected network location.
            if parsed.netloc not in {"", "localhost"}:
                raise ValueError("remote file URIs are not supported")
            path = unquote(parsed.path)
            if os.name == "nt" and len(path) >= 3 and path[0] == "/" and path[2] == ":":
                path = path[1:]
            return Path(path)
        return Path(storage_uri)

    def get(self, storage_uri: str) -> bytes:
        """Read bytes from ``storage_uri``."""
        path = LocalStorageAdapter._path_from_uri(storage_uri)
        if not path.is_file():
            raise FileNotFoundError(storage_uri)
        return path.read_bytes()

    def delete(self, storage_uri: str) -> bool:
        """Delete an object, returning False when it does not exist."""
        path = LocalStorageAdapter._path_from_uri(storage_uri)
        if not path.is_file():
            return False
        path.unlink()
        return True

    def exists(self, storage_uri: str) -> bool:
        """Return whether ``storage_uri`` points to a regular file."""
        return LocalStorageAdapter._path_from_uri(storage_uri).is_file()

    def get_size(self, storage_uri: str) -> int:
        """Return the byte size of an object."""
        path = LocalStorageAdapter._path_from_uri(storage_uri)
        if not path.is_file():
            raise FileNotFoundError(storage_uri)
        return path.stat().st_size


# Descriptive alias for callers that prefer a non-core naming convention.
LocalFileStorage = LocalStorageAdapter

__all__ = ["LocalFileStorage", "LocalStorageAdapter"]
