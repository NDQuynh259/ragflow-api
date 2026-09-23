"""Core File Upload Service coordinating validation and storage persistence."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.storage.services.validator import FileValidator, ValidatedFile

if TYPE_CHECKING:
    from core.storage.ports.storage_port import ObjectStoragePort

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UploadResult:
    """Outcome of a successful file validation and upload process."""

    storage_uri: str
    filename: str
    extension: str
    file_size: int
    content_hash: str
    mime_type: str
    workspace_id: uuid.UUID


class FileUploader:
    """High-level service coordinating file validation, security scanning, and storage upload."""

    def __init__(
        self,
        storage: ObjectStoragePort,
        validator: FileValidator | None = None,
    ) -> None:
        self.storage = storage
        self.validator = validator or FileValidator()

    def upload(
        self,
        filename: str,
        content: bytes,
        workspace_id: uuid.UUID,
        declared_mime_type: str | None = None,
    ) -> UploadResult:
        """Validate file and persist to object storage."""
        logger.info(
            "Initiating file upload for '%s' in workspace %s (%d bytes)",
            filename,
            workspace_id,
            len(content),
        )

        # 1. Run validation, sanitization, and magic-bytes check
        validated: ValidatedFile = self.validator.validate(
            filename=filename,
            content=content,
            declared_mime_type=declared_mime_type,
        )

        # 2. Persist safely into storage
        storage_uri = self.storage.save(
            filename=validated.filename,
            content=validated.content,
            workspace_id=workspace_id,
        )

        logger.info(
            "File '%s' successfully saved to storage URI: %s (hash: %s...)",
            validated.filename,
            storage_uri,
            validated.content_hash[:12],
        )

        return UploadResult(
            storage_uri=storage_uri,
            filename=validated.filename,
            extension=validated.extension,
            file_size=validated.file_size,
            content_hash=validated.content_hash,
            mime_type=validated.detected_mime_type,
            workspace_id=workspace_id,
        )


__all__ = ["FileUploader", "UploadResult"]
