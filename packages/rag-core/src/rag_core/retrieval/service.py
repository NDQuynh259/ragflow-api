"""Retrieval service — embed query, search vector store, return ranked chunks."""

from __future__ import annotations

import logging
import os
from typing import Any

from rag_contracts.chunks import ChunkRecord, SearchResult
from rag_core.embeddings.base import Embedder
from rag_core.ports.vector_store import VectorStore

logger = logging.getLogger(__name__)


class RetrievalService:
    """Retrieve relevant chunks for a query.

    Steps:
    1. Embed the query text.
    2. Search the vector store with optional document/kind filters.
    3. Optionally expand context with neighbor chunks.
    4. Return ranked ``SearchResult`` list.
    """

    def __init__(
        self,
        embedder: Embedder,
        vector_store: VectorStore,
        *,
        default_top_k: int | None = None,
        neighbor_window: int | None = None,
    ) -> None:
        self.embedder = embedder
        self.vector_store = vector_store
        self.default_top_k = default_top_k or int(
            os.environ.get("DEFAULT_TOP_K", "5")
        )
        self.neighbor_window = neighbor_window or int(
            os.environ.get("RAG_NEIGHBOR_WINDOW", "1")
        )

    def retrieve(
        self,
        query: str,
        *,
        document_ids: list[str] | None = None,
        kind: str | None = None,
        top_k: int | None = None,
    ) -> list[SearchResult]:
        """Embed query and search vector store."""
        if not query.strip():
            return []

        k = top_k or self.default_top_k

        # 1. Embed the query
        vectors = self.embedder.embed([query])
        if not vectors:
            logger.warning("Embedding returned empty result for query")
            return []
        query_vector = vectors[0]

        # 2. Build filter
        search_filter: dict[str, Any] = {}
        if document_ids:
            search_filter["document_ids"] = document_ids
        if kind:
            search_filter["kind"] = kind

        # 3. Search
        results = self.vector_store.search(
            query_vector,
            top_k=k,
            filter=search_filter if search_filter else None,
        )

        logger.info(
            "Retrieved %d chunks for query (top_k=%d, filter=%s)",
            len(results),
            k,
            search_filter or "none",
        )

        return results
