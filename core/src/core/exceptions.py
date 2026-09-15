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


class UnauthorizedException(DomainException):
    """Raised when an operation is unauthorized."""
    pass
