"""Structure-preserving table chunking for multimodal RAG.

Mô-đun này cài đặt chiến lược băm bảng biểu (TableChunker) chuyên sâu cho RAG:
1. Bảo toàn cấu trúc Markdown Table:
   - Nếu bảng vừa trong `chunk_size`, giữ nguyên toàn bộ bảng trong 1 chunk.
   - Nếu bảng dài vượt `chunk_size`, cắt theo cửa sổ dòng (Row Windowing) và tự động
     lặp lại phần tiêu đề cột (Header) trên mọi sub-chunk để tránh mất ngữ nghĩa.
2. Xử lý ô siêu dài (Oversized Row / Cell Splitting):
   - Nếu một ô chứa đoạn văn dài hàng nghìn ký tự làm tràn ngân sách của một dòng đơn lẻ,
     hệ thống tự động cắt nhỏ ô đó thành nhiều dòng phụ (sub-rows), giữ nguyên các cột bối cảnh khác.
3. Sinh văn bản tìm kiếm tối ưu (Dense & Lexical Searchable Text):
   - Tạo trường `searchable_text` biểu diễn bảng thành từng cặp "Header = Value" theo từng dòng
     (ví dụ: "Dòng 1: Quý = Q1 | Doanh thu = 150 tỷ VNĐ | Lợi nhuận = 25 tỷ VNĐ").
   - Giúp mô hình vector embedding và BM25 tìm kiếm chính xác giao điểm giữa hàng và cột
     mà không bị nhiễu bởi các ký tự phân cách bảng `| --- |`.
"""

from __future__ import annotations

from typing import Any

from core.uuid7 import uuid7_str
from rag_document_pipeline.models import DocumentChunk, LayoutElement

from ..core import estimate_tokens


class TableChunker:
    """Chiến lược băm bảng biểu bảo toàn cấu trúc bảng Markdown và hỗ trợ tìm kiếm phẳng."""

    def __init__(self, *, chunk_size: int = 1200) -> None:
        """Khởi tạo TableChunker với ngưỡng kích thước ký tự tối đa của một chunk bảng.

        Args:
            chunk_size: Số ký tự tối đa của một chunk bảng; phải là số nguyên dương.
        """
        if chunk_size <= 0:
            raise ValueError("chunk_size phải là số nguyên dương > 0")
        self.chunk_size = chunk_size

    def chunk(
        self,
        elements: list[LayoutElement],
        *,
        document_id: str,
        workspace_id: str = "",
    ) -> list[DocumentChunk]:
        """Chuyển đổi danh sách LayoutElement dạng bảng thành các DocumentChunk độc lập.

        Args:
            elements: Danh sách phần tử bảng đã được chuẩn hóa và gắn caption/footnote.
            document_id: Mã tài liệu sở hữu các chunk tạo thành.
            workspace_id: Mã workspace để cô lập phạm vi truy vấn.

        Returns:
            Danh sách DocumentChunk của mọi phần tử, giữ nguyên thứ tự phần tử đầu vào.
        """
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
        """Thực thi quy trình băm nhỏ một phần tử bảng biểu đơn lẻ.

        Args:
            element: Phần tử bảng cần băm, gồm `table_data`, caption và footnote.
            document_id: Mã tài liệu sở hữu chunk.
            workspace_id: Mã workspace để cô lập phạm vi truy vấn.

        Returns:
            Danh sách chunk của một bảng: một chunk nguyên vẹn hoặc nhiều sub-table
            khi bảng vượt `chunk_size`, mỗi chunk đều lặp lại tiêu đề cột.
        """
        table = element.table_data
        # Trường hợp dự phòng: nếu phần tử không có dữ liệu bảng có cấu trúc
        if not table or (not table.headers and not table.rows):
            content = element.text.strip()
            return (
                [self._make_chunk(document_id, content, element, None, workspace_id=workspace_id)]
                if content
                else []
            )

        caption = table.caption or element.caption or ""
        footnote = element.metadata.get("footnote")
        prefix = f"### {caption}\n\n" if caption else ""
        header = self._render_header(table.headers)
        suffix = f"\n\n_{footnote}_" if footnote else ""
        full = prefix + header + self._render_rows(table.rows) + suffix

        # TRƯỜNG HỢP 1: Toàn bộ bảng vừa vặn trong một chunk đơn lẻ
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

        # TRƯỜNG HỢP 2: Bảng lớn cần cắt theo cửa sổ dòng (Row Windowing)
        chunks: list[DocumentChunk] = []
        current: list[list[str]] = []
        row_start = 0
        was_split = False

        for row_index, row in enumerate(table.rows):
            is_last = row_index == len(table.rows) - 1
            row_suffix = suffix if is_last else ""
            single_row_len = len(prefix + header + self._render_rows([row]) + row_suffix)

            # XỬ LÝ ĐẶC BIỆT: Một dòng đơn lẻ bị tràn vượt quá chunk_size (Oversized Row)
            if single_row_len > self.chunk_size:
                # Xả các dòng đang tích lũy trước đó thành chunk riêng
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

                # Cắt nhỏ dòng bị tràn thành nhiều dòng phụ (sub-rows)
                max_row_len = max(20, self.chunk_size - len(prefix) - len(header) - len(row_suffix))
                sub_rows = self._split_oversized_row(row, max_row_len)
                for idx_sub, sub_r in enumerate(sub_rows):
                    is_last_sub = idx_sub == len(sub_rows) - 1
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

            # TÍCH LŨY DÒNG THƯỜNG VÀO CỬA SỔ HIỆN TẠI
            candidate = current + [row]
            candidate_suffix = suffix if is_last else ""
            candidate_content = prefix + header + self._render_rows(candidate) + candidate_suffix

            if len(candidate_content) <= self.chunk_size or not current:
                current = candidate
                continue

            # Khi thêm dòng mới làm tràn chunk_size: xuất bản chunk hiện tại và mở cửa sổ mới
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

        # Xuất bản lượng dòng còn lại ở cuối bảng
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
        """Kết xuất toàn bộ phần tử bảng thành chuỗi Markdown hoàn chỉnh.

        Args:
            element: Phần tử bảng cần kết xuất.

        Returns:
            Chuỗi Markdown gồm caption, hàng tiêu đề, phân cách và các dòng dữ liệu;
            fallback về `element.text` khi phần tử không có dữ liệu bảng có cấu trúc.
        """
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
        """Chia nhỏ văn bản trong một ô thành các đoạn <= max_chars, ưu tiên dấu ngắt tự nhiên.

        Args:
            text: Nội dung gốc của ô bảng.
            max_chars: Số ký tự tối đa của một đoạn; được kẹp cận tối thiểu bằng 1.

        Returns:
            Danh sách đoạn văn bản, ngắt tại `. `, `? `, `! `, `; `, `, ` hoặc khoảng trắng
            khi có thể, ngược lại cắt cứng tại `max_chars`.
        """
        max_chars = max(1, max_chars)
        current = text.strip()
        if len(current) <= max_chars:
            return [current] if current else [text]

        chunks: list[str] = []
        while len(current) > max_chars:
            cut_point = -1
            # Tìm vị trí ngắt câu hoặc từ gần nhất trước giới hạn max_chars
            for sep in [". ", "? ", "! ", ".\n", "; ", ", ", " "]:
                idx = current.rfind(sep, 0, max_chars)
                if idx != -1:
                    cut_point = idx + len(sep.rstrip())
                    break

            # Nếu không tìm thấy dấu ngắt hợp lý, cắt cứng tại max_chars
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
        """Chia nhỏ một dòng bị tràn kích thước thành nhiều dòng con (sub-rows).

        Thuật toán phân bổ ngân sách:
        1. Tính độ dài định dạng Markdown bảng (overhead: `| ` + ` | `*(N-1) + ` |`).
        2. Nếu chỉ có 1 ô dài đột biến chiếm đa số độ dài:
           - Giữ nguyên các cột ngữ cảnh ngắn xung quanh, chỉ cắt nhỏ ô dài thành nhiều lát cắt.
        3. Nếu nhiều ô đều dài:
           - Phân bổ đều ngân sách ký tự cho từng ô và cắt đồng thời.

        Args:
            row: Hàng dữ liệu gốc dạng danh sách ô.
            max_row_len: Ngân sách ký tự tối đa cho một hàng sau khi trừ overhead Markdown.

        Returns:
            Danh sách các hàng con, mỗi hàng con vẫn giữ đủ số cột của hàng gốc.
        """
        if not row:
            return [row]

        # Độ dài cố định của ký tự phân cách bảng: 3*N + 1
        overhead = 3 * len(row) + 1
        avail = max(10, max_row_len - overhead)

        current_total_len = sum(len(c) for c in row)
        if current_total_len <= avail:
            return [row]

        longest_idx = max(range(len(row)), key=lambda i: len(row[i]))
        other_len = sum(len(row[i]) for i in range(len(row)) if i != longest_idx)

        # Trường hợp 1: Ô dài nhất chiếm trọn ngân sách, các ô khác ngắn
        if other_len < avail:
            cell_budget = max(10, avail - other_len)
            slices = cls._split_text_into_chunks(row[longest_idx], cell_budget)
            sub_rows: list[list[str]] = []
            for s in slices:
                new_row = list(row)
                new_row[longest_idx] = s
                sub_rows.append(new_row)
            return sub_rows

        # Trường hợp 2: Nhiều ô cùng vượt quá ngân sách -> phân bổ đều
        fair_share = max(10, avail // len(row))
        cell_slices = [
            cls._split_text_into_chunks(c, fair_share) if len(c) > fair_share else [c] for c in row
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
        """Kết xuất phần tiêu đề cột Markdown kèm dòng phân cách `| --- |`.

        Args:
            headers: Danh sách tên cột theo thứ tự hiển thị.

        Returns:
            Hai dòng Markdown (tiêu đề + phân cách), hoặc chuỗi rỗng khi không có cột nào.
        """
        if not headers:
            return ""
        return (
            "| " + " | ".join(headers) + " |\n" + "| " + " | ".join("---" for _ in headers) + " |\n"
        )

    @staticmethod
    def _render_rows(rows: list[list[str]]) -> str:
        """Kết xuất các dòng dữ liệu thành định dạng bảng Markdown.

        Args:
            rows: Danh sách hàng dữ liệu, mỗi hàng là list các ô theo thứ tự cột.

        Returns:
            Chuỗi Markdown một dòng mỗi hàng, các ô cách nhau bằng ` | `.
        """
        return "\n".join("| " + " | ".join(row) + " |" for row in rows)

    @staticmethod
    def _render_searchable_text(
        headers: list[str],
        rows: list[list[str]],
        *,
        caption: str = "",
        start_row: int = 1,
    ) -> str:
        """Kết xuất từng dòng của bảng thành các cặp Header = Value rõ ràng cho Dense/BM25 Retrieval.

        Ví dụ đầu ra:
            Bảng: Báo cáo tài chính
            Dòng 1: Quý = Q1 | Doanh thu = 150 tỷ VNĐ | Lợi nhuận = 25 tỷ VNĐ
            Dòng 2: Quý = Q2 | Doanh thu = 180 tỷ VNĐ | Lợi nhuận = 30 tỷ VNĐ

        Args:
            headers: Tên cột dùng làm nhãn cho mỗi cặp key-value.
            rows: Các hàng dữ liệu của sub-table đang kết xuất.
            caption: Tiêu đề bảng, in ở dòng đầu nếu không rỗng.
            start_row: Số thứ tự của hàng đầu tiên, để các sub-table đánh số liên tục.

        Returns:
            Chuỗi text phẳng dạng row-wise key-value; ô trống thành `[empty]` và
            cột thiếu dữ liệu cũng được ghi `= [empty]` để bảo toàn ngữ cảnh cột.
        """
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
        """Đóng gói đối tượng DocumentChunk hoàn chỉnh cho bảng biểu.

        Args:
            document_id: Mã tài liệu sở hữu chunk.
            content: Chuỗi Markdown của sub-table.
            element: Phần tử bảng nguồn, cung cấp trang, bbox, section_path và element id.
            row_range: cặp (row_start, row_end) của các dòng nằm trong chunk; None nếu không cắt hàng.
            repeated_header: Cờ cho biết chunk có lặp lại hàng tiêu đề cột.
            extra: Dict metadata bổ sung được merge sau các key mặc định.
            searchable_text: Bản text phẳng row-wise key-value cho Dense/BM25 retrieval.
            workspace_id: Mã workspace để cô lập phạm vi truy vấn.

        Returns:
            Đối tượng `DocumentChunk` với `kind='table'` và metadata bảng đã hoàn thiện.
        """
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
            id=uuid7_str(),
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


__all__ = ["TableChunker"]
