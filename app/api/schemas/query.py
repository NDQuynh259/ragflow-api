"""API schemas for retrieval, search, and chat."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SearchQueryRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    query: str = Field(..., min_length=1, description="Search query text")
    top_k: int = Field(default=5, ge=1, le=100, description="Top-K vector results")
    search_type: Literal["vector", "hybrid"] = Field(default="hybrid", description="Search strategy")
    document_id: str | None = Field(default=None, description="Optional document ID filter")


class SearchResultChunk(BaseModel):
    chunk_id: str
    document_id: str
    chunk_index: int
    content: str
    metadata: dict[str, Any]
    score: float


class SearchQueryResponse(BaseModel):
    query: str
    top_k: int
    search_type: str
    results: list[SearchResultChunk]


class ChatQueryRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    query: str = Field(..., min_length=1, description="User query question")
    top_k: int = Field(default=5, ge=1, le=100, description="Top-K context chunks to retrieve")
    search_type: Literal["vector", "hybrid"] = Field(default="hybrid", description="Search strategy")
    document_id: str | None = Field(default=None, description="Optional document ID filter")
    system_instruction: str | None = Field(default=None, description="Custom system prompt instructions")


class ChatQueryResponse(BaseModel):
    query: str
    answer: str
    retrieved_contexts: list[SearchResultChunk]
