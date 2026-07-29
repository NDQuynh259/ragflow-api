"""DTOs for document ingestion and document resources."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DocumentResponse(BaseModel):
    id: str
    filename: str
    file_type: str
    file_size: int
    chunk_count: int
    created_at: datetime
    updated_at: datetime
    created_by: str | None
    updated_by: str | None
    deleted_at: datetime | None


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
