"""Multimodal document chunking."""

from .base import Chunker, estimate_tokens
from .image import ImageChunker
from .multimodal import MultimodalChunker
from .section import group_by_section, propagate_sections
from .table import TableChunker
from .text import TextChunker

# Compatibility aliases for existing callers.
HeadingAwareChunker = MultimodalChunker
SemanticTextChunker = TextChunker

__all__ = [
    "Chunker",
    "estimate_tokens",
    "group_by_section",
    "propagate_sections",
    "MultimodalChunker",
    "TextChunker",
    "TableChunker",
    "ImageChunker",
    "HeadingAwareChunker",
    "SemanticTextChunker",
]
