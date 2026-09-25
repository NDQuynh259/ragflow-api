"""Unit tests for FallbackStorageAdapter Outbox and StorageRetrySyncService."""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from core.config import CoreSettings
from core.exceptions import StorageException
from core.storage import (
    FallbackStorageAdapter,
    LocalStorageAdapter,
    ObjectStoragePort,
    StorageRetrySyncService,
    create_storage_adapter,
    create_storage_sync_service,
)


class InMemoryTestTargetStorage(ObjectStoragePort):
    """Simple in-memory storage used to simulate primary S3 target."""

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.should_fail = False

    def save(self, filename: str, content: bytes, workspace_id: uuid.UUID) -> str:
        if self.should_fail:
            raise StorageException("Simulated S3 connection failure!")
        uri = f"s3://test-bucket/workspaces/{workspace_id}/{filename}"
        self.files[uri] = bytes(content)
        return uri

    def get(self, storage_uri: str) -> bytes:
        return self.files[storage_uri]

    def delete(self, storage_uri: str) -> bool:
        if storage_uri in self.files:
            del self.files[storage_uri]
            return True
        return False

    def exists(self, storage_uri: str) -> bool:
        return storage_uri in self.files

    def get_size(self, storage_uri: str) -> int:
        return len(self.files[storage_uri])


def test_fallback_save_creates_outbox_item_on_primary_failure() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        local_adapter = LocalStorageAdapter(base_dir=tmp_path / "files")
        primary_mock = InMemoryTestTargetStorage()
        primary_mock.should_fail = True  # S3 is down!

        fallback_adapter = FallbackStorageAdapter(
            primary=primary_mock,
            secondary=local_adapter,
            outbox_dir=tmp_path / "outbox",
        )

        ws_id = uuid.uuid4()
        content = b"PDF content saved in emergency"
        uri = fallback_adapter.save("report.pdf", content, ws_id)

        # File is safely saved to local disk
        assert uri.startswith("file://")
        assert local_adapter.exists(uri) is True

        # Outbox item is recorded
        pending = fallback_adapter.get_pending_sync_items()
        assert len(pending) == 1
        item = pending[0]
        assert item.local_uri == uri
        assert item.filename == "report.pdf"
        assert item.workspace_id == ws_id
        assert item.retry_count == 0
        assert "Simulated S3 connection failure!" in (item.last_error or "")


def test_storage_retry_sync_service_lifecycle() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        local_adapter = LocalStorageAdapter(base_dir=tmp_path / "files")
        primary = InMemoryTestTargetStorage()
        primary.should_fail = True

        fallback_adapter = FallbackStorageAdapter(
            primary=primary,
            secondary=local_adapter,
            outbox_dir=tmp_path / "outbox",
        )

        ws_id = uuid.uuid4()
        content = b"Document pending sync"
        local_uri = fallback_adapter.save("important.pdf", content, ws_id)

        sync_service = StorageRetrySyncService(
            fallback_adapter=fallback_adapter,
            max_retries=3,
        )

        # 1. Cycle 1: S3 is still down -> retry fails, counter incremented
        results1 = sync_service.sync_pending_files()
        assert len(results1) == 1
        assert results1[0].success is False
        assert local_adapter.exists(local_uri) is True

        pending = fallback_adapter.get_pending_sync_items()
        assert pending[0].retry_count == 1

        # 2. Cycle 2: S3 recovers! -> sync succeeds, DB callback triggered, local deleted
        primary.should_fail = False
        synced_events: list[tuple[str, str, uuid.UUID]] = []

        def on_synced(old_uri: str, new_uri: str, w_id: uuid.UUID) -> None:
            synced_events.append((old_uri, new_uri, w_id))

        results2 = sync_service.sync_pending_files(on_synced_callback=on_synced)
        assert len(results2) == 1
        assert results2[0].success is True
        assert results2[0].s3_uri is not None
        assert results2[0].s3_uri.startswith("s3://test-bucket/")

        # Verify callback received event
        assert len(synced_events) == 1
        assert synced_events[0][0] == local_uri
        assert synced_events[0][1] == results2[0].s3_uri
        assert synced_events[0][2] == ws_id

        # Verify local secondary file and outbox item were cleaned up
        assert local_adapter.exists(local_uri) is False
        assert len(fallback_adapter.get_pending_sync_items()) == 0


def test_storage_retry_sync_exceeds_max_retries() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        local_adapter = LocalStorageAdapter(base_dir=tmp_path / "files")
        primary = InMemoryTestTargetStorage()
        primary.should_fail = True

        fallback_adapter = FallbackStorageAdapter(
            primary=primary,
            secondary=local_adapter,
            outbox_dir=tmp_path / "outbox",
        )

        ws_id = uuid.uuid4()
        fallback_adapter.save("broken.pdf", b"data", ws_id)

        sync_service = StorageRetrySyncService(
            fallback_adapter=fallback_adapter,
            max_retries=2,
        )

        # Fail twice
        sync_service.sync_pending_files()
        sync_service.sync_pending_files()

        # Third attempt: exceeded max retries
        res = sync_service.sync_pending_files()
        assert len(res) == 1
        assert res[0].success is False
        assert "Exceeded max retries" in (res[0].error or "")


def test_create_storage_adapter_and_sync_service_factory(tmp_path: Path) -> None:
    cfg = CoreSettings(
        STORAGE_BACKEND="minio_with_local_fallback",
        STORAGE_DIR=tmp_path,
        MINIO_ENDPOINT="localhost:9000",
        STORAGE_SYNC_MAX_RETRIES=5,
    )

    adapter = create_storage_adapter(cfg)
    assert isinstance(adapter, FallbackStorageAdapter)

    sync_service = create_storage_sync_service(adapter, cfg)
    assert isinstance(sync_service, StorageRetrySyncService)
    assert sync_service.max_retries == 5

    # If backend is pure minio -> sync service is None
    cfg_minio = CoreSettings(STORAGE_BACKEND="minio", STORAGE_DIR=tmp_path)
    adapter_minio = create_storage_adapter(cfg_minio)
    assert create_storage_sync_service(adapter_minio, cfg_minio) is None
