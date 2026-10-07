from __future__ import annotations

from pydantic import BaseModel

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


__all__ = [
    "ElementType",
    "TableData",
    "ImageData",
    "LayoutElement",
    "DocumentChunk",
    "ProcessedDocument",
]
