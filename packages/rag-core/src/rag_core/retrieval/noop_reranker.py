"""No-op reranker that preserves input order."""

from __future__ import annotations

from rag_contracts.chunks import SearchResult


class NoOpReranker:
    """Reranker that returns results unchanged (pass-through)."""

    def rerank(
        self,
        query: str,
        results: list[SearchResult],
        *,
        top_k: int | None = None,
    ) -> list[SearchResult]:
        """Return results in original order, optionally limited to top_k."""
        return results[:top_k] if top_k else results
