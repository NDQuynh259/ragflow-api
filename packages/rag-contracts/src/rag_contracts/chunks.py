"""Chunk contracts shared between document-pipeline and rag-core."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class _ChunkLocation(BaseModel):
    """Fields describing where a chunk came from in the source document."""

    document_id: str
    workspace_id: str = ""
    page_start: int = Field(default=1, ge=1)
    page_end: int = Field(default=1, ge=1)
    element_ids: list[str] = Field(default_factory=list)
    bboxes: list[tuple[float, float, float, float]] = Field(default_factory=list)
    section_path: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_page_range(self) -> _ChunkLocation:
        if self.page_end < self.page_start:
            raise ValueError("page_end must be greater than or equal to page_start")
        return self


class _ChunkPayload(BaseModel):
    """Fields shared by the generated and persisted chunk representations."""

    id: str
    content: str
    kind: str = "text"
    token_count: int = Field(default=0, ge=0)
    indexable: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("content")
    @classmethod
    def _content_is_string(cls, value: str) -> str:
        return value


class DocumentChunk(_ChunkLocation, _ChunkPayload):
    """A chunk produced by the document processing pipeline."""

    index: int = Field(default=0, ge=0)


class ChunkRecord(_ChunkLocation, _ChunkPayload):
    """A chunk ready for vector storage, including its embedding vector."""

    embedding: list[float] = Field(default_factory=list)


class SearchResult(BaseModel):
    """A single vector-search result.

    ``score`` is cosine similarity: higher is better and the expected range is
    ``[-1, 1]`` for normalized pgvector cosine distance.
    """

    chunk: ChunkRecord
    score: float = Field(ge=-1.0, le=1.0)


__all__ = ["ChunkRecord", "DocumentChunk", "SearchResult"]
