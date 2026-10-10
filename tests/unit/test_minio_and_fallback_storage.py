"""Unit tests for MinioStorageAdapter, FallbackStorageAdapter, and storage factory."""

from __future__ import annotations

import uuid
from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.config import CoreSettings
from core.exceptions import FileNotFoundStorageException, StorageException
from core.storage import (
    FallbackStorageAdapter,
    LocalStorageAdapter,
    MinioStorageAdapter,
    ObjectStoragePort,
    create_storage_adapter,
)


class InMemoryMockStorage(ObjectStoragePort):
    """Test fake storage to simulate secondary or test targets."""

    def __init__(self) -> None:
        self._storage: dict[str, bytes] = {}

    def save(self, filename: str, content: bytes, object_path: str) -> str:
        uri = f"memory://{object_path}"
        self._storage[uri] = bytes(content)
        return uri

    def get(self, storage_uri: str) -> bytes:
        if storage_uri not in self._storage:
            raise FileNotFoundStorageException(storage_uri)
        return self._storage[storage_uri]

    def delete(self, storage_uri: str) -> bool:
        if storage_uri in self._storage:
            del self._storage[storage_uri]
            return True
        return False

    def presigned_get_url(self, storage_uri: str, *, expires_in: int = 3600) -> str:
        return storage_uri

    def exists(self, storage_uri: str) -> bool:
        return storage_uri in self._storage

    def get_size(self, storage_uri: str) -> int:
        if storage_uri not in self._storage:
            raise FileNotFoundStorageException(storage_uri)
        return len(self._storage[storage_uri])


def _make_mock_s3_error(code: str = "NoSuchKey", message: str = "Object not found"):
    from minio.error import S3Error

    # S3Error requires response argument
    mock_resp = MagicMock()
    mock_resp.status = 404
    mock_resp.headers = {}
    mock_resp.data = b""
    return S3Error(
        code=code,
        message=message,
        resource="/bucket/key",
        request_id="req123",
        host_id="host123",
        response=mock_resp,
    )


def test_minio_storage_adapter_save_and_ensure_bucket() -> None:
    mock_client = MagicMock()
    mock_client.bucket_exists.return_value = False

    adapter = MinioStorageAdapter(
        endpoint="localhost:9000",
        bucket_name="my-bucket",
        client=mock_client,
    )

    workspace_id = uuid.uuid4()
    content = b"PDF dummy content"
    uri = adapter.save("report.pdf", content, f"workspaces/{workspace_id}/report.pdf")

    # Verifies bucket was created
    mock_client.bucket_exists.assert_called_once_with("my-bucket")
    mock_client.make_bucket.assert_called_once_with("my-bucket", location=None)

    # Verifies put_object was called
    mock_client.put_object.assert_called_once()
    call_kwargs = mock_client.put_object.call_args.kwargs
    assert call_kwargs["bucket_name"] == "my-bucket"
    assert call_kwargs["length"] == len(content)
    assert call_kwargs["object_name"] == f"workspaces/{workspace_id}/report.pdf"

    assert uri.startswith("s3://my-bucket/workspaces/")


def test_local_storage_adapter_presigned_get_url_is_unsupported(tmp_path: Path) -> None:
    adapter = LocalStorageAdapter(base_dir=tmp_path)
    storage_uri = adapter.save("file.txt", b"content", "documents")

    with pytest.raises(StorageException, match="unavailable for local storage"):
        adapter.presigned_get_url(storage_uri, expires_in=120)


def test_local_storage_adapter_rejects_nonpositive_presigned_url_expiry(tmp_path: Path) -> None:
    adapter = LocalStorageAdapter(base_dir=tmp_path)

    with pytest.raises(ValueError, match="expires_in must be positive"):
        adapter.presigned_get_url("file:///tmp/file.txt", expires_in=0)


@pytest.mark.parametrize("expires_in", [0, 604801])
def test_minio_storage_adapter_rejects_expiry_outside_supported_range(expires_in: int) -> None:
    adapter = MinioStorageAdapter(bucket_name="my-bucket", client=MagicMock())

    with pytest.raises(ValueError, match="expires_in must be between 1 and 604800 seconds"):
        adapter.presigned_get_url("s3://my-bucket/doc.pdf", expires_in=expires_in)


@pytest.mark.parametrize("scheme", ["s3", "minio"])
def test_minio_storage_adapter_presigned_get_url_uses_get_method(scheme: str) -> None:
    mock_client = MagicMock()
    adapter = MinioStorageAdapter(bucket_name="my-bucket", client=mock_client)
    mock_client.get_presigned_url.return_value = "https://minio.example/my-bucket/doc.pdf?signature=abc"

    result = adapter.presigned_get_url(f"{scheme}://my-bucket/doc.pdf", expires_in=90)

    assert result == mock_client.get_presigned_url.return_value
    mock_client.get_presigned_url.assert_called_once_with(
        "GET",
        "my-bucket",
        "doc.pdf",
        expires=timedelta(seconds=90),
    )


def test_minio_storage_adapter_presigned_get_url_wraps_client_errors() -> None:
    mock_client = MagicMock()
    mock_client.get_presigned_url.side_effect = RuntimeError("signing failed")
    adapter = MinioStorageAdapter(bucket_name="my-bucket", client=mock_client)

    with pytest.raises(StorageException, match="Failed to create presigned URL"):
        adapter.presigned_get_url("s3://my-bucket/doc.pdf")


def test_fallback_storage_presigned_get_url_routes_by_uri_scheme() -> None:
    primary = MagicMock()
    secondary = MagicMock()
    fallback = FallbackStorageAdapter(primary=primary, secondary=secondary)

    fallback.presigned_get_url("minio://bucket/key", expires_in=300)
    primary.presigned_get_url.assert_called_once_with("minio://bucket/key", expires_in=300)

    fallback.presigned_get_url("file:///tmp/key", expires_in=300)
    secondary.presigned_get_url.assert_called_once_with("file:///tmp/key", expires_in=300)


def test_minio_storage_adapter_get_success() -> None:
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.read.return_value = b"Hello from S3"
    mock_client.get_object.return_value = mock_response

    adapter = MinioStorageAdapter(bucket_name="my-bucket", client=mock_client)
    uri = "s3://my-bucket/workspaces/123/file.pdf"

    data = adapter.get(uri)
    assert data == b"Hello from S3"
    mock_client.get_object.assert_called_once_with("my-bucket", "workspaces/123/file.pdf")
    mock_response.close.assert_called_once()
    mock_response.release_conn.assert_called_once()


def test_minio_storage_adapter_get_not_found() -> None:
    mock_client = MagicMock()
    mock_client.get_object.side_effect = _make_mock_s3_error("NoSuchKey")

    adapter = MinioStorageAdapter(bucket_name="my-bucket", client=mock_client)
    with pytest.raises(FileNotFoundStorageException):
        adapter.get("s3://my-bucket/missing.pdf")


def test_minio_storage_adapter_exists_and_size() -> None:
    mock_client = MagicMock()
    mock_stat = MagicMock()
    mock_stat.size = 1024
    mock_client.stat_object.return_value = mock_stat

    adapter = MinioStorageAdapter(bucket_name="my-bucket", client=mock_client)
    uri = "s3://my-bucket/doc.pdf"

    assert adapter.exists(uri) is True
    assert adapter.get_size(uri) == 1024

    # When object not found
    mock_client.stat_object.side_effect = _make_mock_s3_error("NoSuchKey")
    assert adapter.exists(uri) is False
    with pytest.raises(FileNotFoundStorageException):
        adapter.get_size(uri)


def test_minio_storage_adapter_delete() -> None:
    mock_client = MagicMock()
    adapter = MinioStorageAdapter(bucket_name="my-bucket", client=mock_client)

    uri = "s3://my-bucket/doc.pdf"
    assert adapter.delete(uri) is True
    mock_client.remove_object.assert_called_once_with("my-bucket", "doc.pdf")


def test_fallback_storage_success_primary() -> None:
    primary = InMemoryMockStorage()
    secondary = InMemoryMockStorage()
    fallback = FallbackStorageAdapter(primary=primary, secondary=secondary)

    workspace_id = uuid.uuid4()
    content = b"Content via primary"

    uri = fallback.save("file.txt", content, f"workspaces/{workspace_id}/file.txt")
    assert uri.startswith("memory://")
    # Saved to primary, secondary remains empty
    assert primary.exists(uri) is True
    assert len(secondary._storage) == 0


def test_fallback_storage_fails_over_to_secondary() -> None:
    broken_primary = MagicMock()
    broken_primary.save.side_effect = StorageException("MinIO is down!")

    secondary = InMemoryMockStorage()
    fallback = FallbackStorageAdapter(primary=broken_primary, secondary=secondary)

    workspace_id = uuid.uuid4()
    content = b"Content saved to local fallback"

    uri = fallback.save("fallback_doc.pdf", content, f"workspaces/{workspace_id}/fallback_doc.pdf")
    assert uri.startswith("memory://")
    assert secondary.exists(uri) is True
    assert secondary.get(uri) == content


def test_fallback_storage_routing_by_scheme() -> None:
    primary = MagicMock()
    secondary = MagicMock()
    fallback = FallbackStorageAdapter(primary=primary, secondary=secondary)

    # s3:// routes to primary
    fallback.exists("s3://bucket/key")
    primary.exists.assert_called_once_with("s3://bucket/key")

    fallback.delete("s3://bucket/key")
    primary.delete.assert_called_once_with("s3://bucket/key")

    # file:// routes to secondary
    fallback.exists("file:///path/to/file")
    secondary.exists.assert_called_once_with("file:///path/to/file")

    fallback.delete("file:///path/to/file")
    secondary.delete.assert_called_once_with("file:///path/to/file")


def test_create_storage_adapter_factory() -> None:
    cfg_minio = CoreSettings(
        STORAGE_BACKEND="minio",
        MINIO_ENDPOINT="localhost:9000",
        MINIO_BUCKET_NAME="test-bkt",
    )
    adapter = create_storage_adapter(cfg_minio)
    assert isinstance(adapter, MinioStorageAdapter)
    assert adapter.bucket_name == "test-bkt"
    assert adapter.endpoint == "localhost:9000"
