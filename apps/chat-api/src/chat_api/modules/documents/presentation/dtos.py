"""Presentation DTOs for Documents."""

from __future__ import annotations

from datetime import datetime
from typing import Any
import uuid
from pydantic import BaseModel, Field


class IngestionJobResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    document_id: uuid.UUID
    status: str
    retry_count: int
    parser_name: str
    chunker_name: str
    elapsed_seconds: float | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class DocumentResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    workspace_id: uuid.UUID
    filename: str
    content_hash: str
    mime_type: str
    file_size: int
    status: str
    error_code: str | None = None
    error_message: str | None = None
    page_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
    jobs: list[IngestionJobResponse] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class UploadDocumentResponse(BaseModel):
    document: DocumentResponse
    message: str = "Tài liệu đã được tải lên và đưa vào hàng đợi xử lý."
