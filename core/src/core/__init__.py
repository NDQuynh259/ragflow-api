"""Core shared foundation library for RAG system."""

from __future__ import annotations

from core.config import Settings, settings
from core.exceptions import (
    DomainException,
    DomainValidationException,
    EntityNotFoundException,
    ResourceConflictException,
    UnauthorizedException,
)
from core.logging import setup_logging
from core.uuid7 import uuid7, uuid7_str

__all__ = [
    "DomainException",
    "DomainValidationException",
    "EntityNotFoundException",
    "ResourceConflictException",
    "Settings",
    "UnauthorizedException",
    "settings",
    "setup_logging",
    "uuid7",
    "uuid7_str",
]
