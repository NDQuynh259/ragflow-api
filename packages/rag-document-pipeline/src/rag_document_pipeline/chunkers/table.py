"""Table chunker — preserves table structure and repeats headers.

Small tables are kept as a single chunk.  Large tables are split by row
groups with the header repeated in every chunk so each chunk is
self-contained for retrieval.
"""

from __future__ import annotations

import uuid

from rag_document_pipeline.chunkers.base import estimate_tokens
from rag_document_pipeline.models import DocumentChunk, LayoutElement


class TableChunker:
    """Chunk table elements while preserving structure.

    - Small tables (≤ ``chunk_size`` chars): one chunk.
    - Large tables: split by row groups, header repeated in each chunk.
    - Content rendered as Markdown table.
    """

    def __init__(self, *, chunk_size: int = 1200) -> None:
        self.chunk_size = chunk_size

    def chunk(
        self,
        elements: list[LayoutElement],
        *,
        document_id: str,
    ) -> list[DocumentChunk]:
        chunks: list[DocumentChunk] = []

        for el in elements:
            if not el.table_data and not el.text.strip():
                continue

            table_chunks = self._chunk_table(el, document_id=document_id)
            chunks.extend(table_chunks)

        return chunks

    def _chunk_table(
        self,
        element: LayoutElement,
        *,
        document_id: str,
    ) -> list[DocumentChunk]:
        """Split a single table element into one or more chunks."""
        td = element.table_data

        # Fallback: no structured table data — treat as text chunk
        if not td or (not td.headers and not td.rows):
            content = element.text.strip()
            if not content:
                return []
            return [
                self._make_chunk(
                    document_id=document_id,
                    content=content,
                    element=element,
                    row_range=None,
                )
            ]

        # Build the full markdown table
        header = td.headers
        caption = td.caption or element.caption or ""
        caption_prefix = f"### {caption}\n\n" if caption else ""
        header_md = self._render_header(header)
        footnote = element.metadata.get("footnote")
        footnote_suffix = f"\n\n_{footnote}_" if footnote else ""

        # Try single chunk first
        full_content = caption_prefix + header_md + self._render_rows(td.rows) + footnote_suffix
        if len(full_content) <= self.chunk_size:
            return [
                self._make_chunk(
                    document_id=document_id,
                    content=full_content,
                    element=element,
                    row_range=(0, len(td.rows)),
                )
            ]

        # Split by row groups
        chunks: list[DocumentChunk] = []
        current_rows: list[list[str]] = []
        row_start = 0

        for i, row in enumerate(td.rows):
            current_rows.append(row)
            current_content = caption_prefix + header_md + self._render_rows(current_rows)
            if len(current_content) > self.chunk_size and len(current_rows) > 1:
                # Flush previous rows (excluding current)
                flush_rows = current_rows[:-1]
                flush_content = caption_prefix + header_md + self._render_rows(flush_rows)
                chunks.append(
                    self._make_chunk(
                        document_id=document_id,
                        content=flush_content,
                        element=element,
                        row_range=(row_start, row_start + len(flush_rows)),
                    )
                )
                row_start = i
                current_rows = [row]

        # Flush remaining (append footnote to the final chunk)
        if current_rows:
            remaining_content = (
                caption_prefix
                + header_md
                + self._render_rows(current_rows)
                + footnote_suffix
            )
            chunks.append(
                self._make_chunk(
                    document_id=document_id,
                    content=remaining_content,
                    element=element,
                    row_range=(row_start, row_start + len(current_rows)),
                )
            )

        return chunks

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @classmethod
    def render_markdown(cls, element: LayoutElement) -> str:
        """Render a table LayoutElement into a Markdown string."""
        td = element.table_data
        if not td or (not td.headers and not td.rows):
            return element.text.strip()
        caption = td.caption or element.caption or ""
        caption_prefix = f"### {caption}\n\n" if caption else ""
        header_md = cls._render_header(td.headers)
        rows_md = cls._render_rows(td.rows)
        footnote = element.metadata.get("footnote")
        footnote_suffix = f"\n\n_{footnote}_" if footnote else ""
        return (caption_prefix + header_md + rows_md + footnote_suffix).strip()

    @classmethod
    def is_small_table(
        cls,
        element: LayoutElement,
        *,
        max_chars: int = 800,
        max_rows: int = 10,
    ) -> bool:
        """Check if table is compact enough to be kept inline with text."""
        if element.type.lower() not in ("table", "data_table"):
            return False
        td = element.table_data
        if not td:
            return len(element.text.strip()) <= max_chars
        if len(td.rows) > max_rows:
            return False
        md = cls.render_markdown(element)
        return len(md) <= max_chars

    @staticmethod
    def _render_header(headers: list[str]) -> str:
        if not headers:
            return ""
        header_line = "| " + " | ".join(headers) + " |"
        separator = "| " + " | ".join("---" for _ in headers) + " |"
        return header_line + "\n" + separator + "\n"

    @staticmethod
    def _render_rows(rows: list[list[str]]) -> str:
        lines: list[str] = []
        for row in rows:
            lines.append("| " + " | ".join(row) + " |")
        return "\n".join(lines)

    @staticmethod
    def _make_chunk(
        *,
        document_id: str,
        content: str,
        element: LayoutElement,
        row_range: tuple[int, int] | None,
    ) -> DocumentChunk:
        metadata: dict = {"chunker": "table"}
        if row_range:
            metadata["row_start"] = row_range[0]
            metadata["row_end"] = row_range[1]
            metadata["has_repeated_header"] = True

        return DocumentChunk(
            id=str(uuid.uuid4()),
            document_id=document_id,
            content=content,
            index=0,
            page_start=element.page_number,
            page_end=element.page_number,
            element_ids=[element.id],
            bboxes=[element.bbox] if element.bbox else [],
            kind="table",
            section_path=element.section_path,
            token_count=estimate_tokens(content),
            metadata=metadata,
        )
