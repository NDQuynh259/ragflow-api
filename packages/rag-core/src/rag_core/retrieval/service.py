"""Retrieval service — embed query, search vector store, return ranked chunks."""

from __future__ import annotations

import logging
import os
from typing import Any

from rag_contracts.chunks import SearchResult
from rag_core.ports.embedder import Embedder
from rag_core.ports.reranker import Reranker
from rag_core.ports.vector_store import VectorStore
from rag_core.retrieval.noop_reranker import NoOpReranker

logger = logging.getLogger(__name__)


class RetrievalService:
    """Retrieve relevant chunks for a query.

    Steps:
    1. Embed the query text.
    2. Search the vector store with optional document/kind filters.
    3. Rerank seed results and expand only explicit related-chunk IDs.
    4. Return seeds followed by related ``SearchResult`` items.
    """

    def __init__(
        self,
        embedder: Embedder,
        vector_store: VectorStore,
        *,
        default_top_k: int | None = None,
        neighbor_window: int | None = None,
        reranker: Reranker | None = None,
        rerank_candidate_multiplier: int = 1,
    ) -> None:
        self.embedder = embedder
        self.vector_store = vector_store
        self.reranker = reranker or NoOpReranker()
        self.rerank_candidate_multiplier = rerank_candidate_multiplier
        self.default_top_k = (
            default_top_k if default_top_k is not None else int(os.environ.get("DEFAULT_TOP_K", "5"))
        )
        self.neighbor_window = (
            neighbor_window
            if neighbor_window is not None
            else int(os.environ.get("RAG_NEIGHBOR_WINDOW", "1"))
        )
        if self.default_top_k <= 0:
            raise ValueError("default_top_k must be greater than zero")
        if self.neighbor_window < 0:
            raise ValueError("neighbor_window must not be negative")
        if self.rerank_candidate_multiplier < 1:
            raise ValueError("rerank_candidate_multiplier must be at least 1")

    def retrieve(
        self,
        query: str,
        *,
        document_ids: list[str] | None = None,
        kind: str | None = None,
        top_k: int | None = None,
        workspace_id: str | None = None,
    ) -> list[SearchResult]:
        """Embed query and search vector store."""
        if not query.strip():
            return []

        k = top_k if top_k is not None else self.default_top_k
        if k <= 0:
            raise ValueError("top_k must be greater than zero")

        # 1. Embed the query
        vectors = self.embedder.embed([query])
        if not vectors:
            logger.warning("Embedding returned empty result for query")
            return []
        query_vector = vectors[0]

        # 2. Build filter
        search_filter: dict[str, Any] = {}
        if workspace_id:
            search_filter["workspace_id"] = workspace_id
        if document_ids is not None:
            if not document_ids:
                return []
            search_filter["document_ids"] = document_ids
        if kind:
            search_filter["kind"] = kind

        # 3. Search
        candidate_k = k * self.rerank_candidate_multiplier
        try:
            results = self.vector_store.search(
                query_vector,
                top_k=candidate_k,
                filters=search_filter if search_filter else None,
                query_text=query,
            )
        except TypeError as exc:
            # Preserve compatibility with third-party/legacy VectorStore
            # implementations that predate the optional sparse-query argument.
            if "query_text" not in str(exc):
                raise
            results = self.vector_store.search(
                query_vector,
                top_k=candidate_k,
                filters=search_filter if search_filter else None,
            )

        results = self.reranker.rerank(query, results, top_k=k)
        results = self._expand_related(results, workspace_id=workspace_id)

        logger.info(
            "Retrieved %d chunks for query (top_k=%d, filter=%s)",
            len(results),
            k,
            search_filter or "none",
        )

        return results

    def _expand_related(
        self,
        results: list[SearchResult],
        *,
        workspace_id: str | None,
    ) -> list[SearchResult]:
        """Append explicitly associated chunks without crossing document/workspace scope."""
        if not results or not hasattr(self.vector_store, "get_by_ids"):
            return results

        expanded = list(results)
        seen = {result.chunk.id for result in results}
        requests: dict[tuple[str, str], list[str]] = {}
        for result in results:
            ids = result.chunk.metadata.get("related_chunk_ids", [])
            if not isinstance(ids, list):
                continue
            scope = (result.chunk.workspace_id, result.chunk.document_id)
            for chunk_id in ids:
                if isinstance(chunk_id, str) and chunk_id not in seen:
                    requests.setdefault(scope, []).append(chunk_id)
                    seen.add(chunk_id)

        for (result_workspace, document_id), chunk_ids in requests.items():
            scoped_workspace = workspace_id or result_workspace
            if not scoped_workspace:
                continue
            related = self.vector_store.get_by_ids(
                chunk_ids[: self.neighbor_window or 10],
                workspace_id=scoped_workspace,
                document_id=document_id,
            )
            expanded.extend(related)
        return expanded
