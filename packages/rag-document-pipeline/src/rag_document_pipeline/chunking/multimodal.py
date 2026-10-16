"""Always-on multimodal reading-order chunk router.

Module này điều phối luồng băm nhỏ tài liệu đa phương thức (Multimodal Reading-Order Routing):
1. Nhận danh sách các `LayoutElement` đã qua chuẩn hóa và bóc tách bố cục.
2. Lan truyền ngữ cảnh chương mục (`propagate_sections`) xuống toàn bộ phần tử, duy nhất một lần.
3. Bóc tách nội dung (EXTRACTION, không phải chunking) cho từng phần tử theo thứ tự đọc:
   - Bảng biểu (`table`, `data_table`) -> render thành các khối Markdown (cửa sổ dòng,
     lặp lại tiêu đề) qua `TableChunker` như một bộ biến đổi text.
   - Hình ảnh (`image`, `figure`) -> trích xuất text proxy (caption + Vision VLM) qua
     `ImageChunker.extract_text`.
   - Văn bản thường giữ nguyên.
4. Ghép toàn bộ kết quả extraction vào một dòng text duy nhất theo thứ tự đọc, rồi chạy
   `TextChunker` MỘT LƯỢT DUY NHẤT — ranh giới chunk do ngữ nghĩa (topic shift) quyết định,
   văn bản xung quanh bảng/ảnh nằm chung chunk với chính bảng/ảnh đó.
5. Đánh số chỉ mục `index` tuần tự cho các chunk đầu ra, bảo toàn thứ tự đọc gốc của tài liệu.
"""

from __future__ import annotations

import re
from typing import Any

from rag_document_pipeline.models import DocumentChunk, ElementType, LayoutElement

from .core import (
    DEFAULT_MAX_ASPECT_RATIO,
    DEFAULT_MIN_IMAGE_SIZE,
    Chunker,
    propagate_sections,
)
from .core.constants import IMAGE_TYPES, SKIP_TYPES, TABLE_TYPES
from .strategies import (
    ImageChunker,
    TableChunker,
    TextChunker,
)


class MultimodalChunker:
    """Route text, tables and images to modality-specific chunkers in reading order."""

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
        vision_fn: Any = None,
        triage_enabled: bool = True,
        min_image_size: int = DEFAULT_MIN_IMAGE_SIZE,
        max_aspect_ratio: float = DEFAULT_MAX_ASPECT_RATIO,
        **_,
    ) -> None:
        """Khởi tạo MultimodalChunker với các cấu hình và chiến lược băm con.

        Args:
            chunk_size: Kích thước tối đa của một chunk (áp dụng chung cho text & table).
            text_chunker: Chunker tùy chỉnh cho văn bản; nếu None sẽ tự tạo `TextChunker`.
            table_chunker: Chunker tùy chỉnh cho bảng biểu; nếu None sẽ tự tạo `TableChunker`.
            image_chunker: Chunker tùy chỉnh cho hình ảnh; nếu None sẽ tự tạo `ImageChunker`.
            min_chunk_size: Kích thước tối thiểu của chunk văn bản để tránh các mẩu vụn vặt.
            threshold_percentile: Ngưỡng bách phân vị phát hiện điểm nhảy vọt chủ đề trong `TextChunker`.
            embed_fn: Hàm nhúng vector để tính khoảng cách ngữ nghĩa giữa các câu (tùy chọn).
            vision_fn: Callback gọi mô hình Vision VLM phân tích hình ảnh và trích xuất nội dung.
            triage_enabled: Bật/tắt bộ lọc Triage hình học để loại bỏ ảnh icon/kẻ trang trí.
            min_image_size: Ngưỡng kích thước tối thiểu (px) cho ảnh hợp lệ.
            max_aspect_ratio: Ngưỡng tỷ lệ cạnh tối đa (width/height) để phát hiện đường kẻ/viền.
        """
        self.chunk_size = chunk_size

        # Khởi tạo chiến lược TextChunker (hỗ trợ phân tách ngữ nghĩa chủ đề)
        self.text_chunker = text_chunker or TextChunker(
            embed_fn=embed_fn,
            min_chunk_size=min_chunk_size
            if min_chunk_size is not None
            else min(300, chunk_size // 4),
            max_chunk_size=chunk_size,
            threshold_percentile=threshold_percentile,
        )

        # Khởi tạo chiến lược TableChunker (bảo toàn cấu trúc Markdown table)
        self.table_chunker = table_chunker or TableChunker(chunk_size=chunk_size)

        # Khởi tạo chiến lược ImageChunker (sử dụng duy nhất vision_fn cho hình ảnh)
        self.image_chunker = image_chunker or ImageChunker(
            vision_fn=vision_fn,
            triage_enabled=triage_enabled,
            min_image_size=min_image_size,
            max_aspect_ratio=max_aspect_ratio,
        )

    def chunk(self, elements: list[LayoutElement], *, document_id: str) -> list[DocumentChunk]:
        """Create modality-specific chunks and preserve document reading order."""
        propagated = propagate_sections(elements)
        ordered = [element for element in propagated if element.type.lower() not in SKIP_TYPES]
        chunks: list[DocumentChunk] = []
        text_batch: list[LayoutElement] = []
        active_section_path: list[str] = []
        batch_has_heading = False

        def flush_text() -> None:
            nonlocal batch_has_heading
            if text_batch:
                batch = list(text_batch)
                if active_section_path and not batch_has_heading:
                    for level, title in enumerate(active_section_path, start=1):
                        batch.insert(
                            level - 1,
                            LayoutElement(
                                id=f"section-context-{level}-{title}",
                                type=ElementType.HEADING,
                                text=title,
                                heading_level=level,
                                section_path=list(active_section_path[:level]),
                            ),
                        )
                chunks.extend(self.text_chunker.chunk(batch, document_id=document_id))
                text_batch.clear()
                batch_has_heading = False

        for element in ordered:
            if element.type.lower() == "heading":
                active_section_path = list(element.section_path)
                batch_has_heading = True
            elif element.section_path:
                active_section_path = list(element.section_path)
            kind = element.type.lower()
            if kind in TABLE_TYPES:
                flush_text()
                chunks.extend(self.table_chunker.chunk([element], document_id=document_id))
            elif kind in IMAGE_TYPES:
                flush_text()
                chunks.extend(self.image_chunker.chunk([element], document_id=document_id))
            else:
                text_batch.append(element)
        flush_text()

        self._link_explicit_references(ordered, chunks)
        for index, chunk in enumerate(chunks):
            chunk.index = index
        return chunks

    @staticmethod
    def _link_explicit_references(
        elements: list[LayoutElement], chunks: list[DocumentChunk]
    ) -> None:
        """Link text and modality chunks only for uniquely resolved numbered refs."""
        targets: dict[tuple[str, str], list[DocumentChunk]] = {}
        chunks_by_element = {
            element_id: [chunk for chunk in chunks if element_id in chunk.element_ids]
            for element in elements
            for element_id in [element.id]
        }
        for element in elements:
            if element.type.lower() not in TABLE_TYPES | IMAGE_TYPES:
                continue
            target_chunks = [
                chunk
                for chunk in chunks_by_element.get(element.id, [])
                if chunk.kind in {"table", "figure"}
            ]
            caption = element.caption or (
                element.table_data.caption
                if element.table_data
                else (element.image_data.caption if element.image_data else None)
            )
            match = re.match(
                r"^\s*(Bảng|Table|Hình|Figure|Sơ đồ|Biểu đồ|Chart|Diagram)\s*(\d+(?:\.\d+)*)",
                caption or "",
                re.IGNORECASE,
            )
            if match:
                targets.setdefault((match.group(1).casefold(), match.group(2)), []).extend(
                    target_chunks
                )

        text_chunks = [chunk for chunk in chunks if chunk.kind == "text"]
        for element in elements:
            if element.type.lower() in TABLE_TYPES | IMAGE_TYPES | SKIP_TYPES:
                continue
            references = re.findall(
                r"\b(Bảng|Table|Hình|Figure|Sơ đồ|Biểu đồ|Chart|Diagram)\s*(\d+(?:\.\d+)*)",
                element.text,
                re.IGNORECASE,
            )
            text_chunk = next(
                (chunk for chunk in text_chunks if element.id in chunk.element_ids), None
            )
            if text_chunk is None:
                continue
            for label, number in references:
                matches = targets.get((label.casefold(), number), [])
                if len(matches) != 1:
                    continue
                target = matches[0]
                text_chunk.metadata.setdefault("related_chunk_ids", [])
                target.metadata.setdefault("related_chunk_ids", [])
                if target.id not in text_chunk.metadata["related_chunk_ids"]:
                    text_chunk.metadata["related_chunk_ids"].append(target.id)
                if text_chunk.id not in target.metadata["related_chunk_ids"]:
                    target.metadata["related_chunk_ids"].append(text_chunk.id)
                text_chunk.metadata["association_signal"] = "text_reference"
                target.metadata["association_signal"] = "text_reference"


__all__ = ["MultimodalChunker"]
