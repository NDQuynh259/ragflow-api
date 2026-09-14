"""Chunk contracts shared between document-pipeline and rag-core."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DocumentChunk(BaseModel):
    """A chunk produced by the document processing pipeline."""

    id: str
    document_id: str
    content: str
    index: int = 0
    page_start: int = 1
    page_end: int = 1
    element_ids: list[str] = Field(default_factory=list)
    bboxes: list[tuple[float, float, float, float]] = Field(default_factory=list)
    kind: str = "text"
    section_path: list[str] = Field(default_factory=list)
    token_count: int = 0
    indexable: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChunkRecord(BaseModel):
    """A chunk ready for vector storage.

    This is the contract between the RAG pipeline and the vector store.
    It contains the chunk content, its embedding vector, and all metadata
    required for retrieval and citation.
    """

    id: str
    document_id: str
    content: str
    embedding: list[float] = Field(default_factory=list)
    kind: str = "text"
    page_start: int = 1
    page_end: int = 1
    element_ids: list[str] = Field(default_factory=list)
    bboxes: list[tuple[float, float, float, float]] = Field(default_factory=list)
    section_path: list[str] = Field(default_factory=list)
    token_count: int = 0
    indexable: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResult(BaseModel):
    """A single result returned by vector search."""

    chunk: ChunkRecord
    score: float
