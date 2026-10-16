"""S3/MinIO object storage adapter used for layout staging."""

from __future__ import annotations

import io
import logging
import uuid
from typing import Any
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)


class S3StorageError(RuntimeError):
    """Raised when an S3 operation fails."""


class S3ObjectNotFoundError(FileNotFoundError, S3StorageError):
    """Raised when an object does not exist."""


class S3Storage:
    """Bytes-oriented adapter for AWS S3 and S3-compatible MinIO services."""

    def __init__(
        self,
        bucket_name: str = "rag-documents",
        *,
        endpoint_url: str | None = None,
        region_name: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        session_token: str | None = None,
        client: Any | None = None,
        create_bucket: bool = False,
    ) -> None:
        if not bucket_name or "/" in bucket_name:
            raise ValueError("bucket_name must be a non-empty bucket name")
        self.bucket_name = bucket_name
        self.endpoint_url = endpoint_url
        self.region_name = region_name
        if client is not None:
            self._client = client
        else:
            try:
                import boto3
            except ImportError as exc:  # pragma: no cover
                raise ImportError("boto3 is required for S3Storage") from exc
            kwargs: dict[str, Any] = {"service_name": "s3"}
            for name, value in (
                ("endpoint_url", endpoint_url),
                ("region_name", region_name),
                ("aws_access_key_id", access_key),
                ("aws_secret_access_key", secret_key),
                ("aws_session_token", session_token),
            ):
                if value is not None:
                    kwargs[name] = value
            self._client = boto3.client(**kwargs)
        if create_bucket:
            self._ensure_bucket()

    @property
    def client(self) -> Any:
        return self._client

    def _ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self.bucket_name)
            return
        except Exception:
            pass
        params: dict[str, Any] = {"Bucket": self.bucket_name}
        if self.region_name and self.region_name != "us-east-1":
            params["CreateBucketConfiguration"] = {"LocationConstraint": self.region_name}
        self._client.create_bucket(**params)

    def save(self, filename: str, content: bytes, workspace_id: uuid.UUID | str) -> str:
        """Store bytes and return an ``s3://bucket/key`` URI."""
        if not isinstance(content, bytes):
            raise TypeError("content must be bytes")
        clean_name = filename.replace("\\", "/").rsplit("/", 1)[-1]
        if not clean_name or clean_name in {".", ".."}:
            raise ValueError("filename must contain a file name")
        if clean_name.endswith("_layout.json"):
            key = f"workspaces/{workspace_id}/{clean_name}"
        else:
            key = f"workspaces/{workspace_id}/{uuid.uuid4().hex[:8]}_{clean_name}"
        try:
            self._client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=io.BytesIO(content),
                ContentLength=len(content),
                ContentType="application/json" if clean_name.endswith(".json") else "application/octet-stream",
            )
        except Exception as exc:
            raise S3StorageError(f"failed to store object {key}: {exc}") from exc
        return f"s3://{self.bucket_name}/{key}"

    def get(self, storage_uri: str) -> bytes:
        bucket, key = self._parse_uri(storage_uri)
        try:
            response = self._client.get_object(Bucket=bucket, Key=key)
            body = response["Body"]
            try:
                return body.read()
            finally:
                close = getattr(body, "close", None)
                if close:
                    close()
        except Exception as exc:
            if self._is_not_found(exc):
                raise S3ObjectNotFoundError(storage_uri) from exc
            raise S3StorageError(f"failed to retrieve {storage_uri}: {exc}") from exc

    def delete(self, storage_uri: str) -> bool:
        bucket, key = self._parse_uri(storage_uri)
        try:
            self._client.delete_object(Bucket=bucket, Key=key)
            return True
        except Exception as exc:
            logger.warning("Failed to delete S3 object %s: %s", storage_uri, exc)
            return False

    def exists(self, storage_uri: str) -> bool:
        bucket, key = self._parse_uri(storage_uri)
        try:
            self._client.head_object(Bucket=bucket, Key=key)
            return True
        except Exception as exc:
            if self._is_not_found(exc):
                return False
            raise S3StorageError(f"failed to check {storage_uri}: {exc}") from exc

    def get_size(self, storage_uri: str) -> int:
        bucket, key = self._parse_uri(storage_uri)
        try:
            return int(self._client.head_object(Bucket=bucket, Key=key)["ContentLength"])
        except Exception as exc:
            if self._is_not_found(exc):
                raise S3ObjectNotFoundError(storage_uri) from exc
            raise S3StorageError(f"failed to stat {storage_uri}: {exc}") from exc

    def _parse_uri(self, uri: str) -> tuple[str, str]:
        if not isinstance(uri, str) or not uri:
            raise ValueError("storage_uri must be a non-empty string")
        parsed = urlsplit(uri)
        if parsed.scheme not in {"s3", "minio"} or not parsed.netloc or not parsed.path.lstrip("/"):
            raise ValueError(f"invalid storage URI: {uri!r}")
        return parsed.netloc, parsed.path.lstrip("/")

    @staticmethod
    def _is_not_found(exc: Exception) -> bool:
        response = getattr(exc, "response", {})
        code = str(response.get("Error", {}).get("Code", ""))
        return code in {"404", "NoSuchKey", "NoSuchBucket", "NotFound"}


S3StorageAdapter = S3Storage
MinioStorageAdapter = S3Storage

__all__ = [
    "MinioStorageAdapter",
    "S3ObjectNotFoundError",
    "S3Storage",
    "S3StorageAdapter",
    "S3StorageError",
]
