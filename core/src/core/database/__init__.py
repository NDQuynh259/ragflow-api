"""Shared database base classes, mixins, engine, session, and UnitOfWork."""

from __future__ import annotations

from core.database.base import (
    POSTGRES_NAMING_CONVENTION,
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from core.database.session import SessionLocal, engine, get_db
from core.database.uow import (
    SqlAlchemyUnitOfWork,
    UnitOfWork,
    register_repository,
)

__all__ = [
    "POSTGRES_NAMING_CONVENTION",
    "Base",
    "SessionLocal",
    "SqlAlchemyUnitOfWork",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
    "UnitOfWork",
    "engine",
    "get_db",
    "register_repository",
]
