"""Base chunker protocol and shared utilities."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from rag_document_pipeline.models import DocumentChunk, LayoutElement


@runtime_checkable
class Chunker(Protocol):
    """Protocol for all chunker implementations."""

    def chunk(
        self,
        elements: list[LayoutElement],
        *,
        document_id: str,
    ) -> list[DocumentChunk]:
        """Split elements into indexable chunks."""
        ...


def estimate_tokens(text: str) -> int:
    """Rough token count — ~4 characters per token for multilingual text."""
    return max(1, len(text) // 4)
