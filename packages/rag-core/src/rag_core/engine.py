"""RAG Engine — orchestrates the full index + answer pipeline."""

from __future__ import annotations

import logging
from typing import Any

from rag_contracts import ChunkRecord, DocumentChunk
from rag_core.embeddings.base import Embedder
from rag_core.generation.service import GenerationResult, GenerationService
from rag_core.ports.vector_store import VectorStore
from rag_core.retrieval.service import RetrievalService

logger = logging.getLogger(__name__)


class RAGEngine:
    """Orchestrates embedding, indexing, retrieval, and generation.

    Usage::

        engine = RAGEngine.from_env()
        engine.index(chunks)
        result = engine.answer("Câu hỏi?", document_ids=["doc_123"])
    """

    def __init__(
        self,
        embedder: Embedder,
        vector_store: VectorStore,
        retrieval: RetrievalService,
        generation: GenerationService,
    ) -> None:
        self.embedder = embedder
        self.vector_store = vector_store
        self.retrieval = retrieval
        self.generation = generation

    @classmethod
    def from_env(cls) -> "RAGEngine":
        """Create a RAGEngine with all components configured from env vars."""
        from rag_core.embeddings.gemini import GeminiEmbedder
        from rag_core.indexing.pgvector import PgVectorStore

        embedder = GeminiEmbedder()
        vector_store = PgVectorStore()
        vector_store.ensure_schema()

        retrieval = RetrievalService(
            embedder=embedder,
            vector_store=vector_store,
        )
        generation = GenerationService()

        return cls(
            embedder=embedder,
            vector_store=vector_store,
            retrieval=retrieval,
            generation=generation,
        )

    def index(self, chunks: list[DocumentChunk]) -> int:
        """Embed and store document chunks in the vector store.

        Only indexable chunks with content are embedded.
        Returns the number of chunks stored.
        """
        indexable = [c for c in chunks if c.indexable and c.content.strip()]
        if not indexable:
            logger.info("No indexable chunks to store.")
            return 0

        # Batch embed
        texts = [c.content for c in indexable]
        logger.info("Embedding %d chunks...", len(texts))
        vectors = self.embedder.embed(texts)

        # Build records
        records: list[ChunkRecord] = []
        for chunk, vector in zip(indexable, vectors):
            records.append(
                ChunkRecord(
                    id=chunk.id,
                    document_id=chunk.document_id,
                    workspace_id=getattr(chunk, "workspace_id", ""),
                    content=chunk.content,
                    embedding=vector,
                    kind=chunk.kind,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    element_ids=chunk.element_ids,
                    bboxes=chunk.bboxes,
                    section_path=chunk.section_path,
                    token_count=chunk.token_count,
                    indexable=chunk.indexable,
                    metadata=chunk.metadata,
                )
            )

        # Store
        count = self.vector_store.upsert(records)
        logger.info("Indexed %d chunks.", count)
        return count

    def answer(
        self,
        query: str,
        *,
        document_ids: list[str] | None = None,
        kind: str | None = None,
        top_k: int | None = None,
    ) -> GenerationResult:
        """Retrieve context and generate a grounded answer.

        Args:
            query: The user's question.
            document_ids: Optional list of document IDs to search within.
            kind: Optional chunk kind filter (text, table, figure).
            top_k: Number of chunks to retrieve.

        Returns:
            GenerationResult with answer, citations, and usage.
        """
        # 1. Retrieve
        results = self.retrieval.retrieve(
            query,
            document_ids=document_ids,
            kind=kind,
            top_k=top_k,
        )

        # 2. Generate
        return self.generation.generate(query, results)

    def delete_document(self, document_id: str) -> int:
        """Remove all indexed chunks for a document."""
        return self.vector_store.delete_by_document(document_id)
