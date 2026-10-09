"""Tests for Reranker protocol."""

from __future__ import annotations

import pytest

from rag_contracts.chunks import ChunkRecord, SearchResult
from rag_core.ports.reranker import Reranker


def test_reranker_protocol_is_runtime_checkable():
    """Reranker protocol can verify implementations at runtime."""

    class ValidReranker:
        def rerank(
            self,
            query: str,
            results: list[SearchResult],
            *,
            top_k: int | None = None,
        ) -> list[SearchResult]:
            return results[:top_k] if top_k else results

    instance = ValidReranker()
    assert isinstance(instance, Reranker)


def test_reranker_protocol_rejects_incomplete_implementation():
    """Classes missing required methods don't satisfy protocol."""

    class IncompleteReranker:
        pass

    instance = IncompleteReranker()
    assert not isinstance(instance, Reranker)
