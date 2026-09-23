"""Unit tests for MinioStorageAdapter, FallbackStorageAdapter, and storage factory."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from core.config import CoreSettings
from core.exceptions import FileNotFoundStorageException, StorageException
from core.storage import (
    FallbackStorageAdapter,
    MinioStorageAdapter,
    ObjectStoragePort,
    create_storage_adapter,
)


class InMemoryMockStorage(ObjectStoragePort):
    """Test fake storage to simulate secondary or test targets."""

    def __init__(self) -> None:
        self._storage: dict[str, bytes] = {}

    def save(self, filename: str, content: bytes, workspace_id: uuid.UUID) -> str:
        uri = f"memory://{workspace_id}/{filename}"
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
    uri = adapter.save("report.pdf", content, workspace_id)

    # Verifies bucket was created
    mock_client.bucket_exists.assert_called_once_with("my-bucket")
    mock_client.make_bucket.assert_called_once_with("my-bucket", location=None)

    # Verifies put_object was called
    mock_client.put_object.assert_called_once()
    call_kwargs = mock_client.put_object.call_args.kwargs
    assert call_kwargs["bucket_name"] == "my-bucket"
    assert call_kwargs["length"] == len(content)
    assert f"workspaces/{workspace_id}/" in call_kwargs["object_name"]
    assert call_kwargs["object_name"].endswith("_report.pdf")

    assert uri.startswith("s3://my-bucket/workspaces/")


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

    uri = fallback.save("file.txt", content, workspace_id)
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

    uri = fallback.save("fallback_doc.pdf", content, workspace_id)
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
