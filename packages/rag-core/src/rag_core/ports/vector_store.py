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
        filters: dict[str, Any] | None = None,
        query_text: str | None = None,
    ) -> list[SearchResult]:
        """Search for nearest neighbors. Returns ranked results.

        Args:
            vector: Query embedding.
            top_k: Maximum number of results to return.
            filters: Optional metadata filters (workspace_id, document_ids, kind).
            query_text: Optional raw query text. Backends that support sparse/full-text
                retrieval (e.g. PostgreSQL hybrid search) use it to fuse a keyword
                ranking with the dense ranking; other backends must ignore it and
                fall back to dense-only retrieval.

        Returns:
            Ranked results. With ``query_text``, a backend may return results that
            would not appear in the dense ranking alone.
        """
        ...

    def delete_by_document(self, document_id: str, *, workspace_id: str | None = None) -> int:

        """Delete all chunks belonging to a document. Returns deleted count."""
        ...

    def ensure_schema(self) -> None:
        """Create tables/indexes if they don't exist."""
        ...
