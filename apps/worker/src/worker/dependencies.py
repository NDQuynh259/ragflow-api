"""Worker dependencies and service factories.

Worker initializes its own adapters and services directly from core
and shared packages, completely independent of chat-api.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from core.config import settings
from core.database import SqlAlchemyUnitOfWork
from core.storage import ObjectStoragePort, create_storage_adapter
from rag_core.engine import RAGEngine
from rag_document_pipeline.pipeline import DocumentPipeline

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_storage() -> ObjectStoragePort:
    """Return configured ObjectStorage adapter for worker."""
    return create_storage_adapter(settings)


def get_uow() -> SqlAlchemyUnitOfWork:
    """Return a new UnitOfWork instance for worker transaction boundaries."""
    return SqlAlchemyUnitOfWork()


@lru_cache(maxsize=1)
def get_document_pipeline() -> DocumentPipeline:
    """Return configured DocumentPipeline instance with Hybrid Semantic chunking.

    Cấu hình:
    - Nếu CHUNK_STRATEGY == 'hybrid_semantic': Khởi tạo DocumentPipeline.hybrid_semantic
      kết hợp embed_fn từ RAGEngine (hoặc tự động fallback sang lexical nếu offline).
    - Ngược lại: Sử dụng DocumentPipeline tiêu chuẩn.
    """
    if getattr(settings, "CHUNK_STRATEGY", "hybrid_semantic") == "hybrid_semantic":
        embed_fn = None
        try:
            rag_engine = get_rag_engine()
            if hasattr(rag_engine, "embedder") and hasattr(rag_engine.embedder, "embed"):
                embed_fn = rag_engine.embedder.embed
        except Exception as exc:
            logger.info(
                "RAGEngine embedder not ready for chunking (%s), using lexical fallback",
                exc,
            )

        return DocumentPipeline.hybrid_semantic(
            embed_fn=embed_fn,
            min_chunk_size=getattr(settings, "CHUNK_MIN_SIZE", 300),
            max_chunk_size=getattr(settings, "CHUNK_MAX_SIZE", 1500),
            threshold_percentile=getattr(settings, "CHUNK_THRESHOLD_PERCENTILE", 80.0),
        )

    return DocumentPipeline(
        chunk_size=getattr(settings, "CHUNK_MAX_SIZE", 1200),
    )


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
    "get_document_pipeline",
    "get_rag_engine",
    "get_storage",
    "get_uow",
    "get_worker_command_bus",
]
