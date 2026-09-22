"""Worker dependencies and service factories.

Worker initializes its own adapters and services directly from core
and shared packages, completely independent of chat-api.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from core.config import settings
from core.database import SqlAlchemyUnitOfWork
from core.storage import LocalStorageAdapter, ObjectStoragePort
from rag_core.engine import RAGEngine
from rag_document_pipeline.pipeline import DocumentPipeline

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_storage() -> ObjectStoragePort:
    """Return configured ObjectStorage adapter for worker."""
    return LocalStorageAdapter(base_dir=settings.STORAGE_DIR)


def get_uow() -> SqlAlchemyUnitOfWork:
    """Return a new UnitOfWork instance for worker transaction boundaries."""
    return SqlAlchemyUnitOfWork()


@lru_cache(maxsize=1)
def get_document_pipeline() -> DocumentPipeline:
    """Return configured DocumentPipeline instance."""
    return DocumentPipeline()


@lru_cache(maxsize=1)
def get_rag_engine() -> RAGEngine:
    """Return initialized RAGEngine instance."""
    return RAGEngine.from_env()


def get_worker_command_bus():
    """Build and return a CommandBus wired with worker-level dependencies."""
    import worker.handlers  # noqa: F401
    from core.cqrs import CommandBus, LoggingBehavior
    from core.database import UnitOfWork

    uow = get_uow()
    dependencies = {
        UnitOfWork: uow,
        ObjectStoragePort: get_storage(),
        DocumentPipeline: get_document_pipeline(),
        RAGEngine: get_rag_engine(),
    }

    return CommandBus(
        uow=uow,
        dependencies=dependencies,
        behaviors=[LoggingBehavior()],
    )


__all__ = [
    "get_storage",
    "get_uow",
    "get_document_pipeline",
    "get_rag_engine",
    "get_worker_command_bus",
]
