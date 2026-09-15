"""SQLAlchemy declarative base and common mixins (re-exported from core.database.base)."""

from __future__ import annotations

from core.database.base import (
    POSTGRES_NAMING_CONVENTION,
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)

__all__ = [
    "POSTGRES_NAMING_CONVENTION",
    "Base",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
]
