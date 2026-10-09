"""Structure-preserving table chunking for multimodal RAG."""

from __future__ import annotations

import uuid
from typing import Any

from rag_document_pipeline.chunking.core import estimate_tokens
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
            is_last = (row_index == len(table.rows) - 1)
            row_suffix = suffix if is_last else ""
            single_row_len = len(prefix + header + self._render_rows([row]) + row_suffix)

            if single_row_len > self.chunk_size:
                # Flush pending rows before the oversized row
                if current:
                    chunks.append(
                        self._make_chunk(
                            document_id,
                            prefix + header + self._render_rows(current),
                            element,
                            (row_start, row_index),
                            True,
                            searchable_text=self._render_searchable_text(
                                table.headers, current, caption=caption, start_row=row_start + 1
                            ),
                            workspace_id=workspace_id,
                        )
                    )
                    was_split = True
                    current = []

                # Split the oversized row into multiple sub-table chunks
                max_row_len = max(20, self.chunk_size - len(prefix) - len(header) - len(row_suffix))
                sub_rows = self._split_oversized_row(row, max_row_len)
                for idx_sub, sub_r in enumerate(sub_rows):
                    is_last_sub = (idx_sub == len(sub_rows) - 1)
                    sub_suffix = row_suffix if is_last_sub else ""
                    sub_content = prefix + header + self._render_rows([sub_r]) + sub_suffix
                    chunks.append(
                        self._make_chunk(
                            document_id,
                            sub_content,
                            element,
                            (row_index, row_index + 1),
                            True,
                            searchable_text=self._render_searchable_text(
                                table.headers, [sub_r], caption=caption, start_row=row_index + 1
                            ),
                            workspace_id=workspace_id,
                        )
                    )
                was_split = True
                row_start = row_index + 1
                continue

            candidate = current + [row]
            candidate_suffix = suffix if is_last else ""
            candidate_content = prefix + header + self._render_rows(candidate) + candidate_suffix

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
                        table.headers, current, caption=caption, start_row=row_start + 1
                    ),
                    workspace_id=workspace_id,
                )
            )
            was_split = True
            row_start = row_index
            current = [row]

        if current:
            content = prefix + header + self._render_rows(current) + suffix
            chunks.append(
                self._make_chunk(
                    document_id,
                    content,
                    element,
                    (row_start, row_start + len(current)),
                    was_split,
                    searchable_text=self._render_searchable_text(
                        table.headers, current, caption=caption, start_row=row_start + 1
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

    @staticmethod
    def _split_text_into_chunks(text: str, max_chars: int) -> list[str]:
        """Split long cell text into chunks of at most max_chars, preferring sentence/word boundaries."""
        max_chars = max(1, max_chars)
        current = text.strip()
        if len(current) <= max_chars:
            return [current] if current else [text]

        chunks: list[str] = []
        while len(current) > max_chars:
            cut_point = -1
            for sep in [". ", "? ", "! ", ".\n", "; ", ", ", " "]:
                idx = current.rfind(sep, 0, max_chars)
                if idx != -1:
                    cut_point = idx + len(sep.rstrip())
                    break

            if cut_point <= 0 or cut_point < max_chars // 3:
                cut_point = max_chars

            chunk = current[:cut_point].strip()
            if chunk:
                chunks.append(chunk)
            current = current[cut_point:].strip()

        if current:
            chunks.append(current)
        return chunks or [text]

    @classmethod
    def _split_oversized_row(cls, row: list[str], max_row_len: int) -> list[list[str]]:
        """Split a single oversized row into multiple sub-rows fitting max_row_len."""
        if not row:
            return [row]

        # Markdown table overhead: '| ' (2) + ' | ' * (N - 1) (3*(N-1)) + ' |' (2) = 3*N + 1
        overhead = 3 * len(row) + 1
        avail = max(10, max_row_len - overhead)

        current_total_len = sum(len(c) for c in row)
        if current_total_len <= avail:
            return [row]

        longest_idx = max(range(len(row)), key=lambda i: len(row[i]))
        other_len = sum(len(row[i]) for i in range(len(row)) if i != longest_idx)

        if other_len < avail:
            # Single dominant cell causes the overflow; preserve other context columns
            cell_budget = max(10, avail - other_len)
            slices = cls._split_text_into_chunks(row[longest_idx], cell_budget)
            sub_rows: list[list[str]] = []
            for s in slices:
                new_row = list(row)
                new_row[longest_idx] = s
                sub_rows.append(new_row)
            return sub_rows

        # Multiple cells exceed the budget; divide budget across cells
        fair_share = max(10, avail // len(row))
        cell_slices = [
            cls._split_text_into_chunks(c, fair_share) if len(c) > fair_share else [c]
            for c in row
        ]
        max_slices = max(len(s) for s in cell_slices)
        sub_rows_multi: list[list[str]] = []
        for step in range(max_slices):
            new_row_multi: list[str] = []
            for slices in cell_slices:
                if step < len(slices):
                    new_row_multi.append(slices[step])
                elif len(slices) == 1 and other_len <= avail:
                    new_row_multi.append(slices[0])
                else:
                    new_row_multi.append("")
            sub_rows_multi.append(new_row_multi)
        return sub_rows_multi

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
        start_row: int = 1,
    ) -> str:
        """Render each row as explicit header/value pairs for dense retrieval."""
        prefix = f"Bảng: {caption}\n" if caption else ""
        lines: list[str] = []
        for row_number, row in enumerate(rows, start=start_row):
            pairs = []
            for index, value in enumerate(row):
                label = headers[index].strip() if index < len(headers) else f"Cột {index + 1}"
                normalized = str(value).strip() or "[empty]"
                pairs.append(f"{label} = {normalized}")
            for index in range(len(row), len(headers)):
                label = headers[index].strip() or f"Cột {index + 1}"
                pairs.append(f"{label} = [empty]")
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
