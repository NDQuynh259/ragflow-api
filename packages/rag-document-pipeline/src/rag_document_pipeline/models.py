from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field

class LayoutElement(BaseModel):
    id: str
    type: str
    text: str = ""
    page_number: int = 1
    bbox: tuple[float, float, float, float] | None = None
    source: str | None = None
    caption: str | None = None
    order: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)

class DocumentChunk(BaseModel):
    id: str
    document_id: str
    content: str
    index: int
    page_start: int
    page_end: int
    element_ids: list[str] = Field(default_factory=list)
    bboxes: list[tuple[float, float, float, float]] = Field(default_factory=list)
    kind: str = "text"
    indexable: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

class ProcessedDocument(BaseModel):
    document_id: str
    filename: str
    page_count: int
    elements: list[LayoutElement]
    chunks: list[DocumentChunk]
