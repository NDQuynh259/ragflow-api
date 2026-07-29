"""DTOs for RAG chat."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.dto.search_dto import SearchResultChunk


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
