"""Worker CQRS CommandBus setup and dependency resolution."""

from __future__ import annotations

from core.bus import CommandBus, LoggingBehavior
from core.database import UnitOfWork
from core.storage import ObjectStoragePort
from rag_core.engine import RAGEngine
from rag_document_pipeline.pipeline import DocumentPipeline
from worker.dependencies import (
    get_document_pipeline,
    get_rag_engine,
    get_storage,
    get_uow,
)


def get_worker_command_bus() -> CommandBus:
    """Build and return a CommandBus wired with worker-level dependencies.

    Note: Behaviors use LoggingBehavior without redundant inner transaction wrapping
    since handlers manage atomic boundaries or specific transaction flows internally.
    """
    # Ensure handlers are imported and registered in the command registry
    import worker.handlers  # noqa: F401

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


__all__ = ["get_worker_command_bus"]
