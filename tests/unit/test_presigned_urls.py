from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from core.exceptions import StorageException
from core.storage.adapters.minio import MinioStorageAdapter


def test_minio_presigned_url_generation_success() -> None:
    mock_client = MagicMock()
    mock_client.get_presigned_url.return_value = (
        "https://minio.internal:9000/rag-documents/images/chart.png?sig=123"
    )
    adapter = MinioStorageAdapter(bucket_name="rag-documents", client=mock_client)

    url = adapter.presigned_get_url("s3://rag-documents/images/chart.png", expires_in=1800)

    assert url == "https://minio.internal:9000/rag-documents/images/chart.png?sig=123"
    mock_client.get_presigned_url.assert_called_once_with(
        "GET",
        "rag-documents",
        "images/chart.png",
        expires=timedelta(seconds=1800),
    )


def test_minio_presigned_url_validates_expiry_bounds() -> None:
    adapter = MinioStorageAdapter(bucket_name="rag-documents", client=MagicMock())

    with pytest.raises(ValueError, match="expires_in must be between 1 and 604800"):
        adapter.presigned_get_url("s3://rag-documents/images/chart.png", expires_in=0)

    with pytest.raises(ValueError, match="expires_in must be between 1 and 604800"):
        adapter.presigned_get_url("s3://rag-documents/images/chart.png", expires_in=700000)


def test_minio_presigned_url_wraps_minio_errors() -> None:
    mock_client = MagicMock()
    mock_client.get_presigned_url.side_effect = RuntimeError("network timeout")
    adapter = MinioStorageAdapter(bucket_name="rag-documents", client=mock_client)

    with pytest.raises(StorageException, match="Failed to create presigned URL"):
        adapter.presigned_get_url("s3://rag-documents/images/chart.png")
