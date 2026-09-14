"""SQLAlchemy implementation of Unit of Work."""

from __future__ import annotations

from collections.abc import Generator
from typing import Callable, Self
from fastapi import Depends
from sqlalchemy.orm import Session, sessionmaker

from chat_api.modules.documents.infrastructure.repository import (
    SqlAlchemyDocumentRepository,
)
from chat_api.modules.messages.infrastructure.repository import (
    SqlAlchemyMessageRepository,
)
from chat_api.modules.sessions.infrastructure.repository import (
    SqlAlchemyChatSessionRepository,
)
from chat_api.modules.users.infrastructure.repository import (
    SqlAlchemyUserRepository,
)
from chat_api.modules.workspaces.infrastructure.repository import (
    SqlAlchemyWorkspaceRepository,
)
from chat_api.shared.domain.uow import UnitOfWork
from chat_api.shared.infrastructure.database.session import SessionLocal, get_db


class SqlAlchemyUnitOfWork(UnitOfWork):
    """SQLAlchemy implementation of UnitOfWork across all modules."""

    def __init__(
        self,
        session_factory: Callable[[], Session] = SessionLocal,
        session: Session | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._external_session = session
        self.session: Session | None = session

    def __enter__(self) -> Self:
        if self._external_session is not None:
            self.session = self._external_session
        else:
            self.session = self._session_factory()

        self.sessions = SqlAlchemyChatSessionRepository(self.session)
        self.documents = SqlAlchemyDocumentRepository(self.session)
        self.messages = SqlAlchemyMessageRepository(self.session)
        self.workspaces = SqlAlchemyWorkspaceRepository(self.session)
        self.users = SqlAlchemyUserRepository(self.session)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        try:
            super().__exit__(exc_type, exc_val, exc_tb)
        finally:
            if self._external_session is None and self.session is not None:
                self.session.close()

    def commit(self) -> None:
        if self.session:
            self.session.commit()

    def rollback(self) -> None:
        if self.session:
            self.session.rollback()


def get_uow(db: Session = Depends(get_db)) -> Generator[UnitOfWork, None, None]:
    """FastAPI dependency yielding a UnitOfWork scoped to the current database session."""
    uow = SqlAlchemyUnitOfWork(session=db)
    yield uow
