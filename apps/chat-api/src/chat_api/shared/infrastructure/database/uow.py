"""Generic Unit of Work re-export and FastAPI dependency binding."""

from __future__ import annotations

from collections.abc import Generator

from fastapi import Depends
from sqlalchemy.orm import Session

from core.database import (
    SqlAlchemyUnitOfWork,
    UnitOfWork,
    get_db,
    register_repository,
)


def get_uow(db: Session = Depends(get_db)) -> Generator[UnitOfWork, None, None]:
    """FastAPI dependency yielding a UnitOfWork scoped to the current database session."""
    uow = SqlAlchemyUnitOfWork(session=db)
    yield uow


__all__ = [
    "UnitOfWork",
    "SqlAlchemyUnitOfWork",
    "get_uow",
    "register_repository",
]
