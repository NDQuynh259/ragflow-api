from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# Re-export shared domain contracts from rag_contracts for backwards compatibility
from rag_contracts import (
    DocumentChunk,
    ElementType,
    ImageData,
    LayoutElement,
    TableData,
)

# ---------------------------------------------------------------------------
# Pipeline outputs
# ---------------------------------------------------------------------------


class ProcessedDocument(BaseModel):
    """Final output of the document pipeline."""

    document_id: str
    filename: str
    page_count: int
    elements: list[LayoutElement]
    chunks: list[DocumentChunk]


class ParsedDocument(BaseModel):
    """Intermediate result after parsing and type separation.

    The parser splits raw elements into three lanes so that each chunker
    receives only the element types it knows how to handle.
    """

    document_id: str
    filename: str
    page_count: int
    text_elements: list[LayoutElement] = Field(default_factory=list)
    table_elements: list[LayoutElement] = Field(default_factory=list)
    image_elements: list[LayoutElement] = Field(default_factory=list)
    all_elements: list[LayoutElement] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "ElementType",
    "TableData",
    "ImageData",
    "LayoutElement",
    "DocumentChunk",
    "ProcessedDocument",
    "ParsedDocument",
]
