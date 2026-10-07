"""Errors raised by RAG core components."""

from __future__ import annotations


class RAGCoreError(Exception):
    """Base error for expected RAG-core failures."""


class EmbeddingError(RAGCoreError):
    """Embedding provider returned invalid or incomplete data."""


class VectorStoreError(RAGCoreError):
    """Vector-store operation failed or received invalid input."""


__all__ = ["EmbeddingError", "RAGCoreError", "VectorStoreError"]
