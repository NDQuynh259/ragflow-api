"""Shared domain and application exceptions (re-exported from core.exceptions)."""

from __future__ import annotations

from core.exceptions import (
    DomainException,
    DomainValidationException,
    EntityNotFoundException,
    ForbiddenException,
    ResourceConflictException,
    UnauthenticatedException,
    UnauthorizedException,
)

__all__ = [
    "DomainException",
    "DomainValidationException",
    "EntityNotFoundException",
    "ForbiddenException",
    "ResourceConflictException",
    "UnauthenticatedException",
    "UnauthorizedException",
]
