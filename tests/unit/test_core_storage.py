"""Unit tests for Core FileUploader and ObjectStoragePort interface."""

from __future__ import annotations

import uuid

import pytest

from core.exceptions import (
    EmptyFileException,
    FileNotFoundStorageException,
    FileTooLargeException,
)
from core.storage import (
    FileUploader,
    FileValidator,
    ObjectStoragePort,
)


class InMemoryTestStorage(ObjectStoragePort):
    """Simple in-memory fake storage used exclusively for unit testing."""

    def __init__(self) -> None:
        self._storage: dict[str, bytes] = {}

    def save(self, filename: str, content: bytes, workspace_id: uuid.UUID) -> str:
        file_id = uuid.uuid4().hex[:8]
        safe_name = filename.split("/")[-1].split("\\")[-1]
        uri = f"memory://{workspace_id}/{file_id}_{safe_name}"
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


def test_file_uploader_flow() -> None:
    storage = InMemoryTestStorage()
    validator = FileValidator(max_size_bytes=1024)
    uploader = FileUploader(storage=storage, validator=validator)

    workspace_id = uuid.uuid4()
    content = b"%PDF-1.4 valid test file content"

    result = uploader.upload(
        filename="../../../secret_folder/my_report.pdf",
        content=content,
        workspace_id=workspace_id,
        declared_mime_type="application/pdf",
    )

    # Sanitized filename (no ../ path traversal)
    assert result.filename == "my_report.pdf"
    assert result.extension == ".pdf"
    assert result.file_size == len(content)
    assert result.mime_type == "application/pdf"
    assert result.workspace_id == workspace_id
    assert storage.exists(result.storage_uri) is True
    assert storage.get(result.storage_uri) == content


def test_file_uploader_rejects_empty_and_oversized() -> None:
    storage = InMemoryTestStorage()
    validator = FileValidator(max_size_bytes=50)
    uploader = FileUploader(storage=storage, validator=validator)
    workspace_id = uuid.uuid4()

    # Empty file
    with pytest.raises(EmptyFileException):
        uploader.upload("empty.txt", b"", workspace_id)

    # Oversized file
    with pytest.raises(FileTooLargeException):
        uploader.upload("large.txt", b"x" * 100, workspace_id)
