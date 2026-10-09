"""Always-on multimodal reading-order chunk router."""

from __future__ import annotations

from typing import Any

from rag_document_pipeline.chunking.core import Chunker, group_by_section, propagate_sections
from rag_document_pipeline.chunking.strategies import (
    ImageChunker,
    TableChunker,
    TextChunker,
)
from rag_document_pipeline.models import DocumentChunk, LayoutElement

TEXT_TYPES = {"text", "heading", "paragraph", "list", "caption", "formula"}
TABLE_TYPES = {"table", "data_table"}
IMAGE_TYPES = {"image", "figure"}
SKIP_TYPES = {"header", "footer"}


class MultimodalChunker:
    """Route text, tables, and images independently while preserving context."""

    def __init__(
        self,
        *,
        chunk_size: int = 1200,
        text_chunker: Chunker | None = None,
        table_chunker: TableChunker | None = None,
        image_chunker: ImageChunker | None = None,
        min_chunk_size: int | None = None,
        threshold_percentile: float = 80.0,
        embed_fn: Any = None,
        ocr_fn: Any = None,
        **_,
    ) -> None:
        self.chunk_size = chunk_size
        self.text_chunker = text_chunker or TextChunker(
            embed_fn=embed_fn,
            min_chunk_size=min_chunk_size if min_chunk_size is not None else min(300, chunk_size // 4),
            max_chunk_size=chunk_size,
            threshold_percentile=threshold_percentile,
        )
        self.table_chunker = table_chunker or TableChunker(chunk_size=chunk_size)
        self.image_chunker = image_chunker or ImageChunker(ocr_fn=ocr_fn)

    def chunk(self, elements: list[LayoutElement], *, document_id: str) -> list[DocumentChunk]:
        # Propagate section information to elements
        elements = propagate_sections(elements)

        # Group elements by section path and page number
        groups = group_by_section([e for e in elements if e.type.lower() not in SKIP_TYPES])

        # Iterate through groups and chunk elements
        chunks: list[DocumentChunk] = []
        for group in groups:
            text_batch: list[LayoutElement] = []

            for element in group:
                kind = element.type.lower()
                if kind in TABLE_TYPES:
                    # Flush pending text, then chunk table independently
                    chunks.extend(self._flush_text(text_batch, document_id))
                    text_batch = []
                    chunks.extend(self.table_chunker.chunk([element], document_id=document_id))
                elif kind in IMAGE_TYPES:
                    chunks.extend(self._flush_text(text_batch, document_id))
                    text_batch = []
                    chunks.extend(self.image_chunker.chunk([element], document_id=document_id))
                else:
                    text_batch.append(element)
            chunks.extend(self._flush_text(text_batch, document_id))

        # The traversal already follows parser reading order; retain it rather
        # than sorting by IDs, which are opaque and can reorder modalities.
        for index, chunk in enumerate(chunks):
            chunk.index = index
        return chunks

    # region _flush_text
    def _flush_text(self, elements: list[LayoutElement], document_id: str) -> list[DocumentChunk]:
        if not any(e.text.strip() or e.table_data for e in elements if e.type.lower() != "heading"):
            return []
        return self.text_chunker.chunk(elements, document_id=document_id)


__all__ = ["MultimodalChunker"]

