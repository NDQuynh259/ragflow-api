from typing import List, Dict, Any, Optional, Literal
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, model_validator

class DocumentResponse(BaseModel):
    id: str
    filename: str
    file_type: str
    file_size: int
    chunk_count: int
    created_at: datetime

class IngestTextRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(..., min_length=1, description="Title or filename of text document")
    content: str = Field(..., min_length=1, description="Raw text content to ingest")
    chunk_size: int = Field(default=500, gt=0, le=10000, description="Chunk size in characters")
    chunk_overlap: int = Field(default=50, ge=0, description="Chunk overlap in characters")

    @model_validator(mode="after")
    def validate_chunk_window(self):
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size.")
        return self

class SearchQueryRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    query: str = Field(..., min_length=1, description="Search query text")
    top_k: int = Field(default=5, ge=1, le=100, description="Top-K vector results")
    search_type: Literal["vector", "hybrid"] = Field(default="hybrid", description="Search strategy")
    document_id: Optional[str] = Field(default=None, description="Optional document ID filter")

class SearchResultChunk(BaseModel):
    chunk_id: str
    document_id: str
    chunk_index: int
    content: str
    metadata: Dict[str, Any]
    score: float

class SearchQueryResponse(BaseModel):
    query: str
    top_k: int
    search_type: str
    results: List[SearchResultChunk]

class ChatQueryRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    query: str = Field(..., min_length=1, description="User query question")
    top_k: int = Field(default=5, ge=1, le=100, description="Top-K context chunks to retrieve")
    search_type: Literal["vector", "hybrid"] = Field(default="hybrid", description="Search strategy")
    document_id: Optional[str] = Field(default=None, description="Optional document ID filter")
    system_instruction: Optional[str] = Field(default=None, description="Custom system prompt instructions")

class ChatQueryResponse(BaseModel):
    query: str
    answer: str
    retrieved_contexts: List[SearchResultChunk]

class HealthResponse(BaseModel):
    status: str
    project_name: str
    version: str
    database_connected: bool
    pgvector_extension: bool
    schema_ready: bool
    embedding_provider: str
    llm_provider: str
