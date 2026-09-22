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
]
