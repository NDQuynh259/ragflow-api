"""Retrieval use cases shared by search and chat."""

from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.dto import SearchQueryRequest, SearchQueryResponse, SearchResultChunk
from app.repositories.vector_store_repository import VectorStoreRepository
from app.services.embedding import EmbeddingService


class RetrievalService:
    def __init__(self, embedder: EmbeddingService | None = None) -> None:
        self.embedder = embedder or EmbeddingService()

    def retrieve(self, db: Session, request: SearchQueryRequest) -> list[dict]:
        query_vector = self.embedder.get_embedding(request.query)
        if request.search_type == "vector":
            return VectorStoreRepository.search_vector(
                db, query_vector, request.top_k, request.document_id
            )
        return VectorStoreRepository.search_hybrid(
            db, request.query, query_vector, request.top_k, request.document_id
        )

    def retrieve_rag_contexts(
        self,
        db: Session,
        request: SearchQueryRequest,
    ) -> list[dict[str, Any]]:
        """Retrieve top chunks, expand their neighbors, and merge contiguous context."""
        seed_chunks = self.retrieve(db, request)
        expanded_chunks = VectorStoreRepository.expand_neighbor_chunks(
            db,
            seed_chunks,
            neighbor_window=settings.RAG_NEIGHBOR_WINDOW,
        )
        return self.merge_contiguous_chunks(expanded_chunks)

    @staticmethod
    def merge_contiguous_chunks(
        chunks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Merge adjacent chunks from the same document without duplicating overlap."""
        if not chunks:
            return []

        ordered_chunks = sorted(
            chunks,
            key=lambda chunk: (
                chunk.get("document_rank", 0),
                chunk["document_id"],
                chunk["chunk_index"],
            ),
        )
        groups: list[list[dict[str, Any]]] = []
        for chunk in ordered_chunks:
            if not groups:
                groups.append([chunk])
                continue

            previous = groups[-1][-1]
            is_contiguous = (
                previous["document_id"] == chunk["document_id"]
                and chunk["chunk_index"] == previous["chunk_index"] + 1
            )
            if is_contiguous:
                groups[-1].append(chunk)
            else:
                groups.append([chunk])

        merged_contexts: list[dict[str, Any]] = []
        for group in groups:
            first = group[0]
            last = group[-1]
            content = first["content"]
            for chunk in group[1:]:
                content = RetrievalService._merge_overlapping_text(
                    content,
                    chunk["content"],
                )

            chunk_indexes = [chunk["chunk_index"] for chunk in group]
            chunk_ids = [chunk["chunk_id"] for chunk in group]
            metadata = dict(first.get("metadata") or {})
            metadata.update(
                {
                    "chunk_indexes": chunk_indexes,
                    "chunk_ids": chunk_ids,
                    "expanded_context": len(group) > 1,
                }
            )
            merged_contexts.append(
                {
                    "chunk_id": chunk_ids[0] if len(group) == 1 else f"{chunk_ids[0]}..{chunk_ids[-1]}",
                    "document_id": first["document_id"],
                    "chunk_index": first["chunk_index"],
                    "content": content,
                    "metadata": metadata,
                    "score": max(chunk["score"] for chunk in group),
                    "retrieval_rank": min(
                        chunk.get("retrieval_rank", 0) for chunk in group
                    ),
                }
            )

        merged_contexts.sort(key=lambda context: context["retrieval_rank"])
        for context in merged_contexts:
            context.pop("retrieval_rank", None)
        return merged_contexts

    @staticmethod
    def _merge_overlapping_text(left: str, right: str) -> str:
        """Join two chunks while removing their exact character overlap."""
        max_overlap = min(len(left), len(right), 2_000)
        for overlap_size in range(max_overlap, 0, -1):
            if left[-overlap_size:] == right[:overlap_size]:
                return left + right[overlap_size:]
        return f"{left}\n{right}"

    def search(self, db: Session, request: SearchQueryRequest) -> SearchQueryResponse:
        results = self.retrieve(db, request)
        return SearchQueryResponse(
            query=request.query,
            top_k=request.top_k,
            search_type=request.search_type,
            results=[SearchResultChunk(**result) for result in results],
        )
