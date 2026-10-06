"""Structure-preserving table chunking for multimodal RAG."""

from __future__ import annotations

import uuid
from typing import Any

from rag_document_pipeline.chunking.base import estimate_tokens
from rag_document_pipeline.models import DocumentChunk, LayoutElement


class TableChunker:
    """Render tables as standalone, self-contained Markdown chunks."""

    def __init__(self, *, chunk_size: int = 1200) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        self.chunk_size = chunk_size

    def chunk(
        self,
        elements: list[LayoutElement],
        *,
        document_id: str,
        workspace_id: str = "",
    ) -> list[DocumentChunk]:
        result: list[DocumentChunk] = []
        for element in elements:
            result.extend(
                self._chunk_table(element, document_id=document_id, workspace_id=workspace_id)
            )
        return result

    def _chunk_table(
        self,
        element: LayoutElement,
        *,
        document_id: str,
        workspace_id: str = "",
    ) -> list[DocumentChunk]:
        table = element.table_data
        if not table or (not table.headers and not table.rows):
            content = element.text.strip()
            return [self._make_chunk(document_id, content, element, None, workspace_id=workspace_id)] if content else []

        caption = table.caption or element.caption or ""
        footnote = element.metadata.get("footnote")
        prefix = f"### {caption}\n\n" if caption else ""
        header = self._render_header(table.headers)
        suffix = f"\n\n_{footnote}_" if footnote else ""
        full = prefix + header + self._render_rows(table.rows) + suffix

        if len(full) <= self.chunk_size:
            return [
                self._make_chunk(
                    document_id,
                    full,
                    element,
                    (0, len(table.rows)),
                    False,
                    searchable_text=self._render_searchable_text(
                        table.headers, table.rows, caption=caption
                    ),
                    workspace_id=workspace_id,
                )
            ]

        chunks: list[DocumentChunk] = []
        current: list[list[str]] = []
        row_start = 0
        was_split = False

        for row_index, row in enumerate(table.rows):
            candidate = current + [row]
            candidate_content = prefix + header + self._render_rows(candidate)
            if len(candidate_content) <= self.chunk_size or not current:
                current = candidate
                continue

            chunks.append(
                self._make_chunk(
                    document_id,
                    prefix + header + self._render_rows(current),
                    element,
                    (row_start, row_index),
                    True,
                    searchable_text=self._render_searchable_text(
                        table.headers, table.rows[row_start:row_index], caption=caption
                    ),
                    workspace_id=workspace_id,
                )
            )
            was_split = True
            row_start = row_index
            current = [row]

        if current:
            content = prefix + header + self._render_rows(current) + suffix
            oversized = len(content) > self.chunk_size and len(current) == 1
            metadata_extra = {"oversized_row": True} if oversized else None
            chunks.append(
                self._make_chunk(
                    document_id,
                    content,
                    element,
                    (row_start, row_start + len(current)),
                    was_split,
                    metadata_extra,
                    searchable_text=self._render_searchable_text(
                        table.headers, current, caption=caption
                    ),
                    workspace_id=workspace_id,
                )
            )
        return chunks

    @classmethod
    def render_markdown(cls, element: LayoutElement) -> str:
        table = element.table_data
        if not table or (not table.headers and not table.rows):
            return element.text.strip()
        caption = table.caption or element.caption or ""
        prefix = f"### {caption}\n\n" if caption else ""
        content = prefix + cls._render_header(table.headers) + cls._render_rows(table.rows)
        footnote = element.metadata.get("footnote")
        if footnote:
            content += f"\n\n_{footnote}_"
        return content.strip()

    @classmethod
    def is_small_table(
        cls,
        element: LayoutElement,
        *,
        max_chars: int = 800,
        max_rows: int = 8,
    ) -> bool:
        if element.type.lower() not in {"table", "data_table"}:
            return False
        table = element.table_data
        if table and len(table.rows) > max_rows:
            return False
        return len(cls.render_markdown(element)) <= max_chars

    @staticmethod
    def _render_header(headers: list[str]) -> str:
        if not headers:
            return ""
        return "| " + " | ".join(headers) + " |\n" + "| " + " | ".join("---" for _ in headers) + " |\n"

    @staticmethod
    def _render_rows(rows: list[list[str]]) -> str:
        return "\n".join("| " + " | ".join(row) + " |" for row in rows)

    @staticmethod
    def _render_searchable_text(
        headers: list[str],
        rows: list[list[str]],
        *,
        caption: str = "",
    ) -> str:
        """Render each row as explicit header/value pairs for dense retrieval."""
        prefix = f"Bảng: {caption}\n" if caption else ""
        lines: list[str] = []
        for row_number, row in enumerate(rows, start=1):
            pairs = []
            for index, value in enumerate(row):
                value = str(value).strip()
                if not value:
                    continue
                label = headers[index].strip() if index < len(headers) else f"Cột {index + 1}"
                pairs.append(f"{label} = {value}")
            if pairs:
                lines.append(f"Dòng {row_number}: " + " | ".join(pairs))
        return prefix + "\n".join(lines)

    @staticmethod
    def _make_chunk(
        document_id: str,
        content: str,
        element: LayoutElement,
        row_range: tuple[int, int] | None,
        repeated_header: bool = False,
        extra: dict[str, Any] | None = None,
        *,
        searchable_text: str = "",
        workspace_id: str = "",
    ) -> DocumentChunk:
        metadata: dict[str, Any] = {"chunker": "table", "modality": "table"}
        if row_range is not None:
            metadata.update(row_start=row_range[0], row_end=row_range[1])
        if repeated_header:
            metadata["has_repeated_header"] = True
        if extra:
            metadata.update(extra)
        if searchable_text:
            metadata["searchable_text"] = searchable_text
        return DocumentChunk(
            id=str(uuid.uuid4()),
            document_id=document_id,
            workspace_id=workspace_id,
            content=content,
            page_start=element.page_number,
            page_end=element.page_number,
            element_ids=[element.id],
            bboxes=[element.bbox] if element.bbox else [],
            kind="table",
            section_path=list(element.section_path),
            token_count=estimate_tokens(content),
            metadata=metadata,
        )
