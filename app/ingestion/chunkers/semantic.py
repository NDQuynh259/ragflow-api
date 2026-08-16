"""Lightweight semantic chunker for layout text blocks.

The project does not yet ship a sentence-transformer model for embedding-based
topic boundaries.  Until that adapter is added, paragraph boundaries are kept
intact where possible and oversized paragraphs use the existing recursive
splitter.  The public contract stays compatible with a future semantic model.
"""
from typing import Any

from app.ingestion.chunkers.base import BaseChunker
from app.ingestion.chunkers.recursive import RecursiveChunker


class SemanticChunker(BaseChunker):
    """Split text into semantic chunks."""
    def split(self, text: str, chunk_size: int = 1200, chunk_overlap: int = 200) -> list[dict[str, Any]]:
        if not text or not text.strip():
            return []
        return RecursiveChunker.split_text(text, chunk_size, chunk_overlap)
