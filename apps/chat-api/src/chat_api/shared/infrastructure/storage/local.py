"""Local file system implementation of ObjectStoragePort."""

from __future__ import annotations

from pathlib import Path
import uuid

from chat_api.shared.config import settings
from chat_api.shared.infrastructure.storage.port import ObjectStoragePort


class LocalStorageAdapter(ObjectStoragePort):
    def __init__(self, base_dir: Path | str | None = None) -> None:
        self.base_dir = Path(base_dir or settings.STORAGE_DIR)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, filename: str, content: bytes, workspace_id: uuid.UUID) -> str:
        workspace_dir = self.base_dir / str(workspace_id)
        workspace_dir.mkdir(parents=True, exist_ok=True)

        file_id = uuid.uuid4().hex[:8]
        safe_name = f"{file_id}_{Path(filename).name}"
        target_path = workspace_dir / safe_name
        target_path.write_bytes(content)

        return f"file://{target_path.resolve()}"

    def get(self, storage_uri: str) -> bytes:
        clean_path = storage_uri.replace("file://", "")
        return Path(clean_path).read_bytes()

    def delete(self, storage_uri: str) -> bool:
        clean_path = storage_uri.replace("file://", "")
        path = Path(clean_path)
        if path.exists():
            path.unlink()
            return True
        return False
