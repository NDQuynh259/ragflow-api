"""Generation port for provider-independent RAG orchestration."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from rag_contracts.chunks import SearchResult


@runtime_checkable
class Generator(Protocol):
    """Protocol for grounded answer generation providers."""

    def generate(self, query: str, results: list[SearchResult]):
        """Generate an answer grounded in retrieved results."""
        ...


__all__ = ["Generator"]
