"""Structure Aware chunker (future implementation)."""
from typing import Any
from app.ingestion.chunkers.base import BaseChunker


class StructureAwareChunker(BaseChunker):
    """Split text into structure aware chunks."""
    def split(self, text: str, chunk_size: int = 1200, chunk_overlap: int = 200) -> list[dict[str, Any]]:
        return [{"chunk_index": 0, "content": text}]
