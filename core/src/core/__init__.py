"""Core shared foundation library for RAG system."""

from __future__ import annotations

from core.config import CoreSettings, Settings, settings
from core.domain import AggregateRoot, Entity, ValueObject
from core.exceptions import (
    DomainException,
    DomainValidationException,
    EmptyFileException,
    EntityNotFoundException,
    FileNotFoundStorageException,
    FileTooLargeException,
    FileValidationException,
    ForbiddenException,
    InvalidFileContentException,
    InvalidFileTypeException,
    ResourceConflictException,
    StorageException,
    UnauthenticatedException,
    UnauthorizedException,
)
from core.logging import setup_logging
from core.sse import SSEHub, SSEMessage, SSEResponse, sse_hub
from core.uuid7 import uuid7, uuid7_str

__all__ = [
    "AggregateRoot",
    "Entity",
    "ValueObject",
    "DomainException",
    "DomainValidationException",
    "EmptyFileException",
    "EntityNotFoundException",
    "FileNotFoundStorageException",
    "FileTooLargeException",
    "FileValidationException",
    "ForbiddenException",
    "InvalidFileContentException",
    "InvalidFileTypeException",
    "ResourceConflictException",
    "StorageException",
    "CoreSettings",
    "Settings",
    "UnauthenticatedException",
    "UnauthorizedException",
    "settings",
    "setup_logging",
    "uuid7",
    "uuid7_str",
    "SSEMessage",
    "SSEResponse",
    "SSEHub",
    "sse_hub",
]
