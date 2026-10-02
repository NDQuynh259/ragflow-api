"""Heading-aware chunker — orchestrates type-specific chunkers.

This chunker classifies elements by type and delegates to the appropriate
specialized chunker:

- Text/heading/list/paragraph → SemanticTextChunker (topic shift boundaries & sentence buffer)
- Table → TableChunker (structure-preserving, header-repeating)
- Image/figure → ImageChunker (caption-based)
"""

from __future__ import annotations

from typing import Any

from rag_document_pipeline.chunkers.base import Chunker, group_by_section
from rag_document_pipeline.chunkers.figure import ImageChunker
from rag_document_pipeline.chunkers.semantic import SemanticTextChunker
from rag_document_pipeline.chunkers.table import TableChunker
from rag_document_pipeline.models import DocumentChunk, LayoutElement

# Element types routed to each chunker
TEXT_TYPES = {"text", "heading", "paragraph", "list", "caption", "formula"}
TABLE_TYPES = {"table"}
IMAGE_TYPES = {"image", "figure"}
# Types excluded from chunking (usually page furniture)
SKIP_TYPES = {"header", "footer"}


class HeadingAwareChunker:
    """Orchestrator that routes elements to type-specific chunkers.

    The chunker first separates elements into three lanes (text, table,
    image), then delegates to specialized chunkers.  Results are merged
    and sorted by page position for a natural reading order.
    """

    def __init__(
        self,
        *,
        chunk_size: int = 1200,
        chunk_overlap: int = 200,
        text_chunker: Chunker | None = None,
        table_chunker: TableChunker | None = None,
        image_chunker: ImageChunker | None = None,
        semantic_grouping: bool = True,
    ) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.semantic_grouping = semantic_grouping
        self.text_chunker = text_chunker or SemanticTextChunker(
            min_chunk_size=min(300, chunk_size // 4),
            max_chunk_size=chunk_size,
        )
        self.table_chunker = table_chunker or TableChunker(chunk_size=chunk_size)
        self.image_chunker = image_chunker or ImageChunker()

    # region hybrid_semantic
    @classmethod
    def hybrid_semantic(
        cls,
        *,
        embed_fn: Any = None,
        min_chunk_size: int = 300,
        max_chunk_size: int = 1500,
        threshold_percentile: float = 80.0,
        semantic_grouping: bool = True,
    ) -> HeadingAwareChunker:
        """Create a Hybrid Heading-Aware + Semantic chunker.

        Maintains layout structure, table markdown with repeated headers,
        and uses semantic topic shift boundaries for text blocks.
        """
        return cls(
            chunk_size=max_chunk_size,
            text_chunker=SemanticTextChunker(
                embed_fn=embed_fn,
                min_chunk_size=min_chunk_size,
                max_chunk_size=max_chunk_size,
                threshold_percentile=threshold_percentile,
            ),
            semantic_grouping=semantic_grouping,
        )
    # endregion

    #region chunk
    def chunk(
        self,
        elements: list[LayoutElement],
        *,
        document_id: str,
    ) -> list[DocumentChunk]:
        """Classify elements by type, chunk each lane, merge results."""

        # Propagate section context from headings to subsequent elements
        elements = self._propagate_sections(elements)

        if self.semantic_grouping:
            return self._chunk_semantic_grouping(elements, document_id=document_id)

        # Separate into lanes
        text_elements: list[LayoutElement] = []
        table_elements: list[LayoutElement] = []
        image_elements: list[LayoutElement] = []

        for el in elements:
            el_type = el.type.lower()
            if el_type in SKIP_TYPES:
                continue
            elif el_type in TABLE_TYPES:
                table_elements.append(el)
            elif el_type in IMAGE_TYPES:
                image_elements.append(el)
            elif el_type in TEXT_TYPES:
                text_elements.append(el)
            else:
                # Unknown types go to text
                text_elements.append(el)

        # Chunk each lane
        chunks: list[DocumentChunk] = []
        chunks.extend(self.text_chunker.chunk(text_elements, document_id=document_id))
        chunks.extend(self.table_chunker.chunk(table_elements, document_id=document_id))
        chunks.extend(self.image_chunker.chunk(image_elements, document_id=document_id))

        # Sort by page and re-index
        chunks.sort(key=lambda c: (c.page_start, c.page_end))
        for idx, c in enumerate(chunks):
            c.index = idx

        return chunks
    # endregion

    #region _chunk_semantic_grouping
    def _chunk_semantic_grouping(
        self,
        elements: list[LayoutElement],
        *,
        document_id: str,
    ) -> list[DocumentChunk]:
        """Group elements by section while preserving reading order and context.

        - Small tables are kept inline with their surrounding section text.
        - Large tables exceeding threshold are chunked with TableChunker (repeated headers).
        - Images are processed with ImageChunker.
        """
        groups = self._group_by_section(elements)
        chunks: list[DocumentChunk] = []

        for group in groups:
            text_batch: list[LayoutElement] = []

            def flush_text_batch():
                nonlocal text_batch
                if not text_batch:
                    return
                non_headings = [
                    el
                    for el in text_batch
                    if el.type.lower() != "heading" and (el.text.strip() or el.table_data)
                ]
                if non_headings:
                    text_chunks = self.text_chunker.chunk(text_batch, document_id=document_id)
                    chunks.extend(text_chunks)
                text_batch = []

            for el in group:
                el_type = el.type.lower()
                if el_type in SKIP_TYPES:
                    continue

                if el_type in TABLE_TYPES:
                    if TableChunker.is_small_table(el, max_chars=self.chunk_size // 2, max_rows=8):
                        el_copy = el.model_copy()
                        el_copy.text = TableChunker.render_markdown(el)
                        text_batch.append(el_copy)
                    else:
                        flush_text_batch()
                        table_chunks = self.table_chunker.chunk([el], document_id=document_id)
                        chunks.extend(table_chunks)

                elif el_type in IMAGE_TYPES:
                    flush_text_batch()
                    img_chunks = self.image_chunker.chunk([el], document_id=document_id)
                    chunks.extend(img_chunks)

                else:
                    text_batch.append(el)

            flush_text_batch()

        # Sort by page and re-index
        chunks.sort(key=lambda c: (c.page_start, c.page_end))
        for idx, c in enumerate(chunks):
            c.index = idx

        return chunks
    
    # endregion

    # region _group_by_section  
    _group_by_section = staticmethod(group_by_section)
    
    # endregion

    #region _propagate_sections
    @staticmethod
    def _propagate_sections(
        elements: list[LayoutElement],
    ) -> list[LayoutElement]:
        """Push heading context to subsequent elements that lack one.

        Maintains a heading stack and assigns ``section_path`` to each
        element based on the most recent headings at each level.
        """
        heading_stack: list[tuple[int, str]] = []

        for el in elements:
            if el.type.lower() == "heading" and el.text.strip():
                level = el.heading_level or 1
                # Pop headings at same or deeper level
                heading_stack = [(lvl, txt) for lvl, txt in heading_stack if lvl < level]
                heading_stack.append((level, el.text.strip()))
                el.section_path = [txt for _, txt in heading_stack]
            elif not el.section_path and heading_stack:
                el.section_path = [txt for _, txt in heading_stack]

        return elements
