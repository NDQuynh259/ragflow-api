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
from rag_core.providers.ocr import DualOCRRouter, GeminiOCR, GeminiVisionAnalyzer, TesseractOCR
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

        ocr_fn = _get_ocr_fn()
        vision_fn = _get_vision_analyzer_fn()

        return DocumentPipeline.hybrid_semantic(
            embed_fn=embed_fn,
            ocr_fn=ocr_fn,
            vision_fn=vision_fn,
            min_chunk_size=getattr(settings, "CHUNK_MIN_SIZE", 300),
            max_chunk_size=getattr(settings, "CHUNK_MAX_SIZE", 1500),
            threshold_percentile=getattr(settings, "CHUNK_THRESHOLD_PERCENTILE", 80.0),
        )

    return DocumentPipeline(
        chunk_size=getattr(settings, "CHUNK_MAX_SIZE", 1200),
        ocr_fn=_get_ocr_fn(),
        vision_fn=_get_vision_analyzer_fn(),
    )


@lru_cache(maxsize=1)
def _get_ocr_fn():
    """Return the configured OCR callback, or None when unavailable."""
    if not getattr(settings, "OCR_ENABLED", True):
        return None

    fast_ocr = None
    if getattr(settings, "OCR_FAST_ENABLED", True):
        try:
            fast_ocr = TesseractOCR(lang=getattr(settings, "OCR_FAST_LANG", "eng+vie"))
        except Exception as exc:
            logger.warning("Fast OCR unavailable: %s", exc)

    vlm_ocr = None
    try:
        vlm_ocr = GeminiOCR(model=getattr(settings, "OCR_MODEL", "gemini-2.0-flash"))
    except Exception as exc:
        logger.warning("VLM OCR unavailable: %s", exc)

    if fast_ocr and vlm_ocr:
        return DualOCRRouter(fast_ocr=fast_ocr, vlm_ocr=vlm_ocr)
    return fast_ocr or vlm_ocr


@lru_cache(maxsize=1)
def _get_vision_analyzer_fn():
    """Return the configured vision analyzer, or None when unavailable."""
    if not getattr(settings, "VISION_ANALYSIS_ENABLED", True):
        return None
    try:
        return GeminiVisionAnalyzer(model=getattr(settings, "VISION_MODEL", "gemini-2.0-flash"))
    except Exception as exc:
        logger.warning("Vision analysis unavailable: %s", exc)
        return None


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
