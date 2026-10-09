"""Reranking protocol for retrieval candidates."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from rag_contracts.chunks import SearchResult


@runtime_checkable
class Reranker(Protocol):
    """Protocol for providers that reorder retrieved candidates."""

    def rerank(
        self,
        query: str,
        results: list[SearchResult],
        *,
        top_k: int | None = None,
    ) -> list[SearchResult]:
        """Return candidates ordered by relevance to query."""
        ...
