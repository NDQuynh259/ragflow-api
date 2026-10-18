"""Shared domain contracts across the workspace."""

from .chunks import ChunkRecord, DocumentChunk, SearchResult
from .elements import ElementType, ImageData, LayoutElement, TableData
from .ir import DocumentIR, ElementIR, SectionIR, SourceLocation

__all__ = [
    "ChunkRecord",
    "DocumentIR",
    "ElementIR",
    "SectionIR",
    "SourceLocation",
    "DocumentChunk",
    "SearchResult",
    "ElementType",
    "ImageData",
    "LayoutElement",
    "TableData",
]
