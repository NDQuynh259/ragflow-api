"""Vector store protocol."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from rag_contracts.chunks import ChunkRecord, SearchResult


@runtime_checkable
class VectorStore(Protocol):
    """Protocol for vector storage backends."""

    def upsert(self, records: list[ChunkRecord]) -> int:
        """Insert or update chunk records. Returns count of upserted records."""
        ...

    def search(
        self,
        vector: list[float],
        *,
        top_k: int = 5,
        filter: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Search for nearest neighbors. Returns ranked results."""
        ...

    def delete_by_document(self, document_id: str) -> int:
        """Delete all chunks belonging to a document. Returns deleted count."""
        ...

    def ensure_schema(self) -> None:
        """Create tables/indexes if they don't exist."""
        ...
