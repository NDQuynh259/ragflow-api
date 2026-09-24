"""Resilient Fallback Storage Adapter with Outbox tracking for background retry sync."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from core.config import settings
from core.storage.ports.storage_port import ObjectStoragePort

logger = logging.getLogger(__name__)


@dataclass
class OutboxItem:
    """Represents a file saved locally awaiting retry synchronization to primary storage."""

    local_uri: str
    filename: str
    workspace_id: uuid.UUID
    created_at: str
    retry_count: int = 0
    last_error: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> OutboxItem:
        return cls(
            local_uri=data["local_uri"],
            filename=data["filename"],
            workspace_id=uuid.UUID(str(data["workspace_id"])),
            created_at=data["created_at"],
            retry_count=data.get("retry_count", 0),
            last_error=data.get("last_error"),
        )

    def to_dict(self) -> dict:
        d = asdict(self)
        d["workspace_id"] = str(self.workspace_id)
        return d


class FallbackStorageAdapter(ObjectStoragePort):
    """Storage adapter that attempts primary storage first (e.g. MinIO/S3),

    and automatically falls back to secondary storage (e.g. local server) if primary fails,
    recording an outbox metadata manifest for subsequent background retry.
    """

    def __init__(
        self,
        primary: ObjectStoragePort,
        secondary: ObjectStoragePort,
        outbox_dir: Path | str | None = None,
    ) -> None:
        self.primary = primary
        self.secondary = secondary
        self.outbox_dir = Path(outbox_dir or (Path(settings.STORAGE_DIR) / "outbox"))
        self.outbox_dir.mkdir(parents=True, exist_ok=True)

    def save(self, filename: str, content: bytes, workspace_id: uuid.UUID) -> str:
        """Attempt primary upload first. If error occurs, fall back immediately to secondary and record outbox."""
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

            # Record into outbox for background retry sync
            self._record_outbox(
                local_uri=fallback_uri,
                filename=filename,
                workspace_id=workspace_id,
                error_msg=str(exc),
            )
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

    # -------------------------------------------------------------------------
    # Outbox Management
    # -------------------------------------------------------------------------

    def _get_outbox_path(self, local_uri: str) -> Path:
        """Derive deterministic filename in outbox for a given local URI."""
        import hashlib

        uri_hash = hashlib.sha256(local_uri.encode("utf-8")).hexdigest()[:16]
        return self.outbox_dir / f"outbox_{uri_hash}.json"

    def _record_outbox(
        self,
        local_uri: str,
        filename: str,
        workspace_id: uuid.UUID,
        error_msg: str,
    ) -> None:
        """Persist metadata JSON tracking this local file for subsequent retry."""
        item = OutboxItem(
            local_uri=local_uri,
            filename=filename,
            workspace_id=workspace_id,
            created_at=datetime.now(UTC).isoformat(),
            retry_count=0,
            last_error=error_msg,
        )
        outbox_file = self._get_outbox_path(local_uri)
        outbox_file.write_text(json.dumps(item.to_dict(), indent=2), encoding="utf-8")
        logger.info("Recorded Outbox retry item for '%s': %s", filename, outbox_file.name)

    def get_pending_sync_items(self) -> list[OutboxItem]:
        """Scan outbox directory and return all pending OutboxItems."""
        items: list[OutboxItem] = []
        if not self.outbox_dir.exists():
            return items

        for file_path in self.outbox_dir.glob("outbox_*.json"):
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                items.append(OutboxItem.from_dict(data))
            except Exception as exc:
                logger.warning("Corrupted outbox file '%s': %s", file_path, exc)

        return sorted(items, key=lambda x: x.created_at)

    def update_outbox_item(self, item: OutboxItem) -> None:
        """Update an existing outbox item metadata (e.g. increment retry count)."""
        outbox_file = self._get_outbox_path(item.local_uri)
        outbox_file.write_text(json.dumps(item.to_dict(), indent=2), encoding="utf-8")

    def mark_synced(self, local_uri: str) -> None:
        """Remove outbox metadata once primary upload and DB update have succeeded."""
        outbox_file = self._get_outbox_path(local_uri)
        if outbox_file.exists():
            outbox_file.unlink()
            logger.info("Cleared Outbox manifest for %s", local_uri)


__all__ = ["FallbackStorageAdapter", "OutboxItem"]
