"""Shared domain and application exceptions."""

from __future__ import annotations

from typing import Any


class DomainException(Exception):
    """Base domain exception."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class EntityNotFoundException(DomainException):
    """Raised when an entity is not found."""

    def __init__(self, entity_name: str, entity_id: Any) -> None:
        super().__init__(
            f"{entity_name} with id '{entity_id}' not found.",
            details={"entity_name": entity_name, "entity_id": str(entity_id)},
        )


class DomainValidationException(DomainException):
    """Raised when a business rule or invariant is violated."""

    pass


class ResourceConflictException(DomainException):
    """Raised when a resource conflict occurs."""

    pass


class UnauthenticatedException(DomainException):
    """Raised when credentials are missing, invalid, or expired."""

    pass


class ForbiddenException(DomainException):
    """Raised when an authenticated principal lacks permission."""

    pass


class UnauthorizedException(ForbiddenException):
    """Deprecated compatibility alias; use a precise auth exception."""

    pass


class NonRetriableQueueError(Exception):
    """Marker exception indicating that a queue message processing failure should not be retried."""

    pass


class AccountSuspendedException(ForbiddenException, NonRetriableQueueError):
    """Raised when an account or workspace is inactive, locked, or suspended."""

    def __init__(
        self,
        message: str = "Account or workspace is inactive or suspended.",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details=details)


class FileValidationException(DomainValidationException):
    """Base exception for file validation failures."""

    pass


class FileTooLargeException(FileValidationException):
    """Raised when an uploaded file exceeds the configured maximum size."""

    def __init__(self, size: int, max_size: int) -> None:
        super().__init__(
            f"File size of {size} bytes exceeds maximum allowed limit of {max_size} bytes.",
            details={"file_size": size, "max_size": max_size},
        )


class EmptyFileException(FileValidationException):
    """Raised when an uploaded file is empty (0 bytes)."""

    def __init__(self, filename: str = "") -> None:
        super().__init__(
            f"Uploaded file '{filename}' is empty (0 bytes).",
            details={"filename": filename},
        )


class InvalidFileTypeException(FileValidationException):
    """Raised when an uploaded file has a disallowed extension or MIME type."""

    def __init__(self, filename: str, mime_type: str | None, allowed: list[str]) -> None:
        super().__init__(
            f"File '{filename}' with MIME type '{mime_type}' is not supported. Allowed formats: {', '.join(allowed)}.",
            details={"filename": filename, "mime_type": mime_type, "allowed": allowed},
        )


class InvalidFileContentException(FileValidationException):
    """Raised when an uploaded file's binary magic bytes do not match its declared type."""

    def __init__(self, filename: str, expected_type: str, reason: str = "") -> None:
        msg = f"File content mismatch for '{filename}': expected {expected_type}."
        if reason:
            msg += f" {reason}"
        super().__init__(msg, details={"filename": filename, "expected_type": expected_type})


class StorageException(DomainException):
    """Base exception for storage errors."""

    pass


class FileNotFoundStorageException(StorageException, EntityNotFoundException):
    """Raised when a storage URI cannot be found or read."""

    def __init__(self, storage_uri: str) -> None:
        super().__init__(
            entity_name="StorageObject",
            entity_id=storage_uri,
        )


__all__ = [
    "DomainException",
    "EntityNotFoundException",
    "DomainValidationException",
    "ResourceConflictException",
    "UnauthenticatedException",
    "ForbiddenException",
    "UnauthorizedException",
    "NonRetriableQueueError",
    "AccountSuspendedException",
    "FileValidationException",
    "FileTooLargeException",
    "EmptyFileException",
    "InvalidFileTypeException",
    "InvalidFileContentException",
    "StorageException",
    "FileNotFoundStorageException",
]
