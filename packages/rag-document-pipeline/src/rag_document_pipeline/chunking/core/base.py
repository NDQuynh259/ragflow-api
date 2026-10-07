"""Base chunker protocol."""

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


__all__ = [
    "Chunker",
]
