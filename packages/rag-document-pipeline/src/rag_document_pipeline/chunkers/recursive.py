"""Text chunker using LangChain RecursiveCharacterTextSplitter.

Groups adjacent text elements within the same section, prepends heading
context, then splits using LangChain's recursive strategy.
"""

from __future__ import annotations

import uuid

from langchain_text_splitters import RecursiveCharacterTextSplitter

from rag_document_pipeline.chunkers.base import estimate_tokens
from rag_document_pipeline.models import DocumentChunk, LayoutElement

# Element types handled by this chunker
TEXT_TYPES = {"text", "heading", "paragraph", "list", "caption", "formula"}


class TextChunker:
    """Chunk text elements using LangChain's RecursiveCharacterTextSplitter.

    Adjacent text elements within the same section are concatenated before
    splitting.  Headings are prepended as context so each chunk is
    self-contained when retrieved independently.
    """

    def __init__(
        self,
        *,
        chunk_size: int = 1200,
        chunk_overlap: int = 200,
    ) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", ", ", " ", ""],
            length_function=len,
        )

    def chunk(
        self,
        elements: list[LayoutElement],
        *,
        document_id: str,
    ) -> list[DocumentChunk]:
        """Group by section, prepend heading, split with LangChain."""
        if not elements:
            return []

        # Group adjacent elements by section
        groups = self._group_by_section(elements)
        chunks: list[DocumentChunk] = []

        for group in groups:
            heading_prefix = self._heading_prefix(group)
            body = "\n\n".join(
                el.text.strip() for el in group if el.text.strip() and el.type != "heading"
            )
            full_text = f"{heading_prefix}\n\n{body}".strip() if heading_prefix else body.strip()

            if not full_text:
                continue

            # Collect provenance from the group
            all_pages = [el.page_number for el in group]
            all_ids = [el.id for el in group]
            all_bboxes = [el.bbox for el in group if el.bbox]
            section_path = group[0].section_path if group else []

            # Split using LangChain
            split_texts = self._splitter.split_text(full_text)

            for text_piece in split_texts:
                if not text_piece.strip():
                    continue
                chunks.append(
                    DocumentChunk(
                        id=str(uuid.uuid4()),
                        document_id=document_id,
                        content=text_piece,
                        index=len(chunks),
                        page_start=min(all_pages),
                        page_end=max(all_pages),
                        element_ids=all_ids,
                        bboxes=all_bboxes,
                        kind="text",
                        section_path=section_path,
                        token_count=estimate_tokens(text_piece),
                        metadata={"chunker": "text_recursive"},
                    )
                )

        return chunks

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _group_by_section(
        elements: list[LayoutElement],
    ) -> list[list[LayoutElement]]:
        """Group adjacent elements sharing the same section path."""
        if not elements:
            return []

        groups: list[list[LayoutElement]] = []
        current: list[LayoutElement] = [elements[0]]

        for el in elements[1:]:
            prev = current[-1]
            same_section = el.section_path == prev.section_path
            same_page = el.page_number == prev.page_number
            # Break on section or page boundary
            if same_section and same_page:
                current.append(el)
            else:
                groups.append(current)
                current = [el]
        groups.append(current)
        return groups

    @staticmethod
    def _heading_prefix(group: list[LayoutElement]) -> str:
        """Extract heading text from the group for context prefix."""
        headings = [el.text.strip() for el in group if el.type == "heading" and el.text.strip()]
        if headings:
            return "## " + " > ".join(headings)
        if group and group[0].section_path:
            return "## " + " > ".join(group[0].section_path)
        return ""
