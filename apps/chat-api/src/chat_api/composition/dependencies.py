"""Composition Root — centralised dependency providers.

All concrete adapter instantiation happens here so that presentation routers
only depend on abstract *ports*, never on concrete implementations.  This is
the single place that wires adapters to ports for the entire application.
"""

from __future__ import annotations

from chat_api.shared.rag.adapter import RAGEngineAdapter
from chat_api.shared.rag.port import RAGEnginePort
from core.queue.background import BackgroundQueueAdapter
from core.queue.port import IngestionQueuePort
from core.storage.local import LocalStorageAdapter
from core.storage.port import ObjectStoragePort

# ---------------------------------------------------------------------------
# Singleton adapter instances (created once at import time)
# ---------------------------------------------------------------------------
_storage = LocalStorageAdapter()
_queue = BackgroundQueueAdapter()
_rag_engine = RAGEngineAdapter()


# ---------------------------------------------------------------------------
# FastAPI dependency callables — return abstract port types
# ---------------------------------------------------------------------------
def get_storage() -> ObjectStoragePort:
    """Provide the application-wide object storage adapter."""
    return _storage


def get_queue() -> IngestionQueuePort:
    """Provide the application-wide ingestion queue adapter."""
    return _queue


def get_rag_engine() -> RAGEnginePort:
    """Provide the application-wide RAG engine adapter."""
    return _rag_engine


__all__ = [
    "get_storage",
    "get_queue",
    "get_rag_engine",
]
