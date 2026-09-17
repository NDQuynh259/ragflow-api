"""Shared database models and Unit of Work for chat-api."""

from __future__ import annotations

from core.database import (
    POSTGRES_NAMING_CONVENTION,
    Base,
    SessionLocal,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    engine,
    get_db,
)
from chat_api.shared.database.uow import SqlAlchemyUnitOfWork, UnitOfWork, get_uow

__all__ = [
    "Base",
    "POSTGRES_NAMING_CONVENTION",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
    "SessionLocal",
    "engine",
    "get_db",
    "UnitOfWork",
    "SqlAlchemyUnitOfWork",
    "get_uow",
]
