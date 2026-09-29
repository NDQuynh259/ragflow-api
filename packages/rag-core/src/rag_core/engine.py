"""RAG Engine — orchestrates the full index + answer pipeline."""

from __future__ import annotations

import logging

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
    def from_env(cls) -> RAGEngine:
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

    def index(self, chunks: list[DocumentChunk], batch_size: int = 50) -> int:
        """Embed and store document chunks in the vector store in micro-batches.

        Only indexable chunks with content are embedded.
        Processes in batches of `batch_size` (default: 50) to prevent RAM spikes and memory bloat.
        Returns the number of chunks stored.
        """
        indexable = [c for c in chunks if c.indexable and c.content.strip()]
        if not indexable:
            logger.info("No indexable chunks to store.")
            return 0

        total_indexed = 0
        total_chunks = len(indexable)

        for i in range(0, total_chunks, batch_size):
            batch = indexable[i : i + batch_size]
            texts = [c.content for c in batch]
            logger.info(
                "Embedding batch %d-%d of %d chunks...",
                i + 1,
                min(i + batch_size, total_chunks),
                total_chunks,
            )
            vectors = self.embedder.embed(texts)

            records: list[ChunkRecord] = [
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
                for chunk, vector in zip(batch, vectors, strict=False)
            ]

            count = self.vector_store.upsert(records)
            total_indexed += count

        logger.info("Indexed %d chunks in total.", total_indexed)
        return total_indexed

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
