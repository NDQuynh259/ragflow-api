"""Shared domain contracts across the workspace."""

from .chunks import ChunkRecord, DocumentChunk, SearchResult
from .elements import ElementType, ImageData, LayoutElement, TableData

__all__ = [
    "ChunkRecord",
    "DocumentChunk",
    "SearchResult",
    "ElementType",
    "ImageData",
    "LayoutElement",
    "TableData",
]
