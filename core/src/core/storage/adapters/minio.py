"""MinIO / S3-compatible implementation of ObjectStoragePort."""

from __future__ import annotations

import io
import logging
import uuid
from typing import TYPE_CHECKING

from core.exceptions import FileNotFoundStorageException, StorageException
from core.storage.ports.storage_port import ObjectStoragePort

if TYPE_CHECKING:
    from minio import Minio

logger = logging.getLogger(__name__)


class MinioStorageAdapter(ObjectStoragePort):
    """Adapter for storing and retrieving objects from MinIO or S3-compatible storage."""

    def __init__(
        self,
        endpoint: str = "localhost:9000",
        access_key: str = "minioadmin",
        secret_key: str = "minioadmin",
        bucket_name: str = "rag-documents",
        secure: bool = False,
        region: str | None = None,
        client: Minio | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket_name = bucket_name
        self.secure = secure
        self.region = region

        if client is not None:
            self._client = client
        else:
            from minio import Minio

            self._client = Minio(
                endpoint=self.endpoint,
                access_key=self.access_key,
                secret_key=self.secret_key,
                secure=self.secure,
                region=self.region,
            )

        self._bucket_verified = False

    @property
    def client(self) -> Minio:
        return self._client

    def _ensure_bucket(self) -> None:
        if not self._bucket_verified:
            try:
                if not self._client.bucket_exists(self.bucket_name):
                    self._client.make_bucket(self.bucket_name, location=self.region)
                    logger.info("MinIO bucket '%s' created successfully.", self.bucket_name)
                self._bucket_verified = True
            except Exception as exc:
                logger.warning(
                    "Could not verify/create MinIO bucket '%s': %s", self.bucket_name, exc
                )
                raise

    def save(self, filename: str, content: bytes, workspace_id: uuid.UUID) -> str:
        self._ensure_bucket()
        file_id = uuid.uuid4().hex[:8]
        clean_name = filename.split("/")[-1].split("\\")[-1]
        object_key = f"workspaces/{workspace_id}/{file_id}_{clean_name}"

        content_stream = io.BytesIO(content)
        self._client.put_object(
            bucket_name=self.bucket_name,
            object_name=object_key,
            data=content_stream,
            length=len(content),
        )

        return f"s3://{self.bucket_name}/{object_key}"

    def get(self, storage_uri: str) -> bytes:
        bucket, object_key = self._parse_uri(storage_uri)
        from minio.error import S3Error

        try:
            response = self._client.get_object(bucket, object_key)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()
        except S3Error as err:
            if err.code in ("NoSuchKey", "NoSuchBucket"):
                raise FileNotFoundStorageException(storage_uri) from err
            raise StorageException(f"MinIO S3 error: {err.message}") from err
        except Exception as exc:
            raise StorageException(f"Failed to retrieve {storage_uri}: {exc}") from exc

    def delete(self, storage_uri: str) -> bool:
        bucket, object_key = self._parse_uri(storage_uri)
        try:
            self._client.remove_object(bucket, object_key)
            return True
        except Exception as exc:
            logger.warning("Failed to delete MinIO object %s: %s", storage_uri, exc)
            return False

    def exists(self, storage_uri: str) -> bool:
        bucket, object_key = self._parse_uri(storage_uri)
        from minio.error import S3Error

        try:
            self._client.stat_object(bucket, object_key)
            return True
        except S3Error as err:
            if err.code in ("NoSuchKey", "NoSuchBucket"):
                return False
            raise
        except Exception:
            return False

    def get_size(self, storage_uri: str) -> int:
        bucket, object_key = self._parse_uri(storage_uri)
        from minio.error import S3Error

        try:
            stat = self._client.stat_object(bucket, object_key)
            if stat.size is None:
                raise StorageException(f"Object size could not be determined for {storage_uri}")
            return stat.size
        except S3Error as err:
            if err.code in ("NoSuchKey", "NoSuchBucket"):
                raise FileNotFoundStorageException(storage_uri) from err
            raise StorageException(f"MinIO S3 error: {err.message}") from err

    def _parse_uri(self, uri: str) -> tuple[str, str]:
        clean = uri
        for prefix in ("s3://", "minio://"):
            if clean.startswith(prefix):
                clean = clean[len(prefix) :]
                break
        parts = clean.split("/", 1)
        if len(parts) == 2:
            return parts[0], parts[1]
        return self.bucket_name, clean


__all__ = ["MinioStorageAdapter"]
