"""Core shared foundation library for RAG system."""

from __future__ import annotations

from core.config import CoreSettings, Settings, settings
from core.exceptions import (
    DomainException,
    DomainValidationException,
    EntityNotFoundException,
    ForbiddenException,
    ResourceConflictException,
    UnauthenticatedException,
    UnauthorizedException,
)
from core.domain import AggregateRoot, Entity, ValueObject
from core.logging import setup_logging
from core.uuid7 import uuid7, uuid7_str

__all__ = [
    "AggregateRoot",
    "Entity",
    "ValueObject",
    "DomainException",
    "DomainValidationException",
    "EntityNotFoundException",
    "ForbiddenException",
    "ResourceConflictException",
    "CoreSettings",
    "Settings",
    "UnauthenticatedException",
    "UnauthorizedException",
    "settings",
    "setup_logging",
    "uuid7",
    "uuid7_str",
]
