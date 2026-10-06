"""Local file system implementation of ObjectStoragePort."""

from __future__ import annotations

from pathlib import Path

from core.config import settings
from core.storage.ports.storage_port import ObjectStoragePort


class LocalStorageAdapter(ObjectStoragePort):
    """Adapter for storing and retrieving objects on the local server file system."""

    def __init__(self, base_dir: Path | str | None = None) -> None:
        self.base_dir = Path(base_dir or settings.STORAGE_DIR)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        filename: str,
        content: bytes,
        object_path: str,
    ) -> str:
        relative_path = Path(object_path)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ValueError("object_path must be a safe relative path")
        target_path = self.base_dir / relative_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(content)

        return f"file://{target_path.resolve()}"

    def get(self, storage_uri: str) -> bytes:
        clean_path = storage_uri.replace("file://", "")
        path = Path(clean_path)
        if not path.is_file():
            from core.exceptions import FileNotFoundStorageException

            raise FileNotFoundStorageException(storage_uri)
        return path.read_bytes()

    def delete(self, storage_uri: str) -> bool:
        clean_path = storage_uri.replace("file://", "")
        path = Path(clean_path)
        if path.exists():
            path.unlink()
            return True
        return False

    def exists(self, storage_uri: str) -> bool:
        clean_path = storage_uri.replace("file://", "")
        return Path(clean_path).is_file()

    def get_size(self, storage_uri: str) -> int:
        clean_path = storage_uri.replace("file://", "")
        path = Path(clean_path)
        if not path.is_file():
            from core.exceptions import FileNotFoundStorageException

            raise FileNotFoundStorageException(storage_uri)
        return path.stat().st_size


__all__ = ["LocalStorageAdapter"]
