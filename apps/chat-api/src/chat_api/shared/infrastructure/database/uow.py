"""Generic Unit of Work interface and SQLAlchemy implementation.

Provides transaction boundary management and generic repository resolution:
    repo = uow.get_repo(DocumentRepository)

Repositories are registered at the Composition Root (chat_api.composition.dependencies)
so that this module has ZERO dependencies on specific domain modules.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Generator
from contextlib import contextmanager
from typing import Any, Self, TypeVar

from fastapi import Depends
from sqlalchemy.orm import Session

from core.database import SessionLocal, get_db

T = TypeVar("T")

RepoFactory = Callable[[Session], Any]

# Global registry: interface_class -> factory callable (Session -> ConcreteRepo)
_REPO_REGISTRY: dict[type, RepoFactory] = {}

# Backward-compatibility alias map: "documents" -> DocumentRepository
_REPO_ALIASES: dict[str, type] = {}


def register_repository(
    interface_cls: type[T],
    factory: RepoFactory,
    aliases: str | list[str] | None = None,
) -> None:
    """Register mapping between an abstract repository interface and its concrete factory.

    Optionally binds alias string(s) (e.g. 'documents', 'chat_sessions') for
    backward-compatible property access via uow.<alias>.
    """
    _REPO_REGISTRY[interface_cls] = factory
    if aliases:
        if isinstance(aliases, str):
            aliases = [aliases]
        for alias in aliases:
            _REPO_ALIASES[alias] = interface_cls


class UnitOfWork(ABC):
    """Abstract Unit of Work context manager ensuring atomic transaction boundaries
    and generic repository resolution.
    """

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        try:
            if exc_type is not None:
                self.rollback()
                self.discard_new_events()
            else:
                try:
                    self.commit()
                except Exception:
                    self.rollback()
                    self.discard_new_events()
                    raise
        finally:
            self.close()

    @contextmanager
    def read_only(self) -> Generator[Self, None, None]:
        """Open repositories for a query and never commit its transaction."""
        self.__enter__()
        try:
            yield self
        finally:
            try:
                self.rollback()
            finally:
                self.close()

    def track(self, *aggregates: Any) -> None:
        """Track aggregates whose domain events should be published after commit."""
        tracked = getattr(self, "_tracked_aggregates", None)
        if tracked is None:
            tracked = []
            self._tracked_aggregates = tracked
        for aggregate in aggregates:
            if not any(candidate is aggregate for candidate in tracked):
                tracked.append(aggregate)

    def collect_new_events(self) -> list[Any]:
        events: list[Any] = []
        tracked = getattr(self, "_tracked_aggregates", [])
        for aggregate in tracked:
            poll_events = getattr(aggregate, "poll_events", None)
            if poll_events is not None:
                events.extend(poll_events())
        tracked.clear()
        return events

    def discard_new_events(self) -> None:
        """Drop events produced by a transaction that did not commit."""
        tracked = getattr(self, "_tracked_aggregates", [])
        for aggregate in tracked:
            poll_events = getattr(aggregate, "poll_events", None)
            if poll_events is not None:
                poll_events()
        tracked.clear()

    def close(self) -> None:
        """Release resources owned by this Unit of Work."""

    @abstractmethod
    def commit(self) -> None:
        """Commit the current transaction."""
        pass

    @abstractmethod
    def rollback(self) -> None:
        """Rollback the current transaction."""
        pass

    def get_repo(self, repo_cls: type[T]) -> T:
        """Dynamically resolve and return a repository bound to this transaction."""
        for alias, registered_cls in _REPO_ALIASES.items():
            if registered_cls is repo_cls and hasattr(self, alias):
                return getattr(self, alias)
        raise NotImplementedError(
            f"'{type(self).__name__}' does not implement 'get_repo' for '{repo_cls.__name__}'."
        )

    def __getattr__(self, name: str) -> Any:
        """Fallback dynamic resolution for registered aliases (e.g. uow.documents)."""
        if name in _REPO_ALIASES:
            return self.get_repo(_REPO_ALIASES[name])
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")


class SqlAlchemyUnitOfWork(UnitOfWork):
    """SQLAlchemy implementation of UnitOfWork with generic repository resolution."""

    def __init__(
        self,
        session_factory: Callable[[], Session] = SessionLocal,
        session: Session | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._external_session = session
        self.session: Session | None = session
        self._repo_cache: dict[type, Any] = {}

    def __enter__(self) -> Self:
        if self._external_session is not None:
            self.session = self._external_session
        else:
            self.session = self._session_factory()
        self._repo_cache.clear()
        return self

    def get_repo(self, repo_cls: type[T]) -> T:
        """Resolve a repository instance bound to the active transaction."""
        if self.session is None:
            raise RuntimeError("Cannot access repository outside of an active UnitOfWork context.")

        if repo_cls not in self._repo_cache:
            factory = _REPO_REGISTRY.get(repo_cls)
            if factory is not None:
                instance = factory(self.session)
            elif callable(repo_cls):
                # Fallback: if repo_cls can be directly instantiated with session
                try:
                    repo_factory: Any = repo_cls
                    instance = repo_factory(self.session)
                except TypeError as err:
                    raise KeyError(
                        f"Repository '{repo_cls.__name__}' is not registered in the UnitOfWork registry "
                        f"and could not be instantiated directly: {err}"
                    ) from err
            else:
                raise KeyError(
                    f"Repository interface '{repo_cls.__name__}' is not registered in UnitOfWork."
                )
            self._repo_cache[repo_cls] = instance

        return self._repo_cache[repo_cls]  # type: ignore[return-value]

    def commit(self) -> None:
        if self.session:
            self.session.commit()

    def rollback(self) -> None:
        if self.session:
            self.session.rollback()

    def close(self) -> None:
        if self._external_session is None and self.session is not None:
            self.session.close()


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
