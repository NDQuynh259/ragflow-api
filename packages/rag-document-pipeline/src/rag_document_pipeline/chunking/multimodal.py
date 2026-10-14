"""Always-on multimodal reading-order chunk router.

Module này điều phối luồng băm nhỏ tài liệu đa phương thức (Multimodal Reading-Order Routing):
1. Nhận danh sách các `LayoutElement` đã qua chuẩn hóa và bóc tách bố cục.
2. Lan truyền ngữ cảnh chương mục (`propagate_sections`) để mọi phần tử đều mang đường dẫn phân cấp (`section_path`).
3. Gom nhóm theo thứ tự đọc tự nhiên (`group_by_section`), tránh xáo trộn dòng đọc giữa văn bản, bảng biểu và hình ảnh.
4. Điều phối từng loại phần tử đến chiến lược xử lý chuyên biệt:
   - Văn bản thường (`text`, `paragraph`, `list`...) -> gom đệm và gửi sang `TextChunker`.
   - Bảng biểu (`table`, `data_table`) -> xả văn bản chờ, xử lý độc lập qua `TableChunker`.
   - Hình ảnh (`image`, `figure`) -> xả văn bản chờ, xử lý độc lập qua `ImageChunker` (sử dụng mô hình `vision_fn`).
5. Đánh số chỉ mục `index` tuần tự cho các chunk đầu ra, bảo toàn thứ tự đọc gốc của tài liệu.
"""

from __future__ import annotations

from typing import Any

from rag_document_pipeline.models import DocumentChunk, LayoutElement

from .core import (
    DEFAULT_MAX_ASPECT_RATIO,
    DEFAULT_MIN_IMAGE_SIZE,
    Chunker,
    group_by_section,
    propagate_sections,
)
from .core.constants import IMAGE_TYPES, SKIP_TYPES, TABLE_TYPES
from .strategies import (
    ImageChunker,
    TableChunker,
    TextChunker,
)


class MultimodalChunker:
    """Bộ điều phối băm nhỏ tài liệu đa phương thức theo thứ tự đọc tự nhiên.

    Định tuyến các phần tử văn bản, bảng biểu và hình ảnh đến từng chiến lược băm chuyên biệt,
    đồng thời bảo toàn trọn vẹn ngữ cảnh chương mục và thứ tự xuất hiện gốc trong trang.
    """

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
        """Thực hiện băm nhỏ danh sách LayoutElement theo thứ tự đọc của tài liệu.

        Quy trình xử lý:
        1. Lan truyền thông tin phân cấp tiêu đề (`propagate_sections`) xuống từng phần tử.
        2. Gom nhóm các phần tử liên tục theo cùng `section_path` và `page_number`.
        3. Duyệt tuần tự qua từng nhóm:
           - Tích lũy các phần tử text vào `text_batch`.
           - Khi gặp Table hoặc Image, xả hàng đợi text hiện tại (`_flush_text`) rồi băm độc lập phần tử đó.
        4. Gán chỉ mục `chunk.index` tăng dần, bảo toàn 100% thứ tự đọc gốc.

        Args:
            elements: Danh sách phần tử layout sau bước chuẩn hóa (bỏ header/footer khi gom nhóm).
            document_id: Mã tài liệu gán cho mọi chunk tạo thành.

        Returns:
            Danh sách DocumentChunk đã đánh số `index` liên tiếp theo thứ tự đọc của tài liệu.
        """
        # 1. Lan truyền cây chương mục xuống toàn bộ phần tử
        elements = propagate_sections(elements)

        # 2. Gom nhóm theo section_path và số trang, bỏ qua header/footer
        groups = group_by_section([e for e in elements if e.type.lower() not in SKIP_TYPES])

        # 3. Duyệt qua từng nhóm để phân làn xử lý
        chunks: list[DocumentChunk] = []
        for group in groups:
            text_batch: list[LayoutElement] = []

            for element in group:
                kind = element.type.lower()
                if kind in TABLE_TYPES:
                    # Gặp bảng biểu: Xả văn bản chờ phía trước, sau đó băm bảng độc lập
                    chunks.extend(self._flush_text(text_batch, document_id))
                    text_batch = []
                    chunks.extend(self.table_chunker.chunk([element], document_id=document_id))
                elif kind in IMAGE_TYPES:
                    # Gặp hình ảnh: Xả văn bản chờ phía trước, sau đó băm ảnh độc lập
                    chunks.extend(self._flush_text(text_batch, document_id))
                    text_batch = []
                    chunks.extend(self.image_chunker.chunk([element], document_id=document_id))
                else:
                    # Tích lũy các phần tử văn bản thông thường
                    text_batch.append(element)

            # Xả lượng văn bản còn lại ở cuối nhóm
            chunks.extend(self._flush_text(text_batch, document_id))

        # 4. Đánh lại index tuần tự theo đúng thứ tự đọc của tài liệu
        for index, chunk in enumerate(chunks):
            chunk.index = index
        return chunks

    # region _flush_text
    def _flush_text(self, elements: list[LayoutElement], document_id: str) -> list[DocumentChunk]:
        """Xả hàng đợi các phần tử văn bản và gửi sang TextChunker.

        Bỏ qua các lô chỉ chứa tiêu đề đứng một mình mà không có nội dung văn bản kèm theo,
        tránh tạo ra các chunk chỉ toàn heading rỗng.

        Args:
            elements: Lô phần tử văn bản đang chờ trong hàng đợi.
            document_id: Mã tài liệu gán cho các chunk trả về.

        Returns:
            Danh sách chunk từ `TextChunker`, hoặc danh sách rỗng nếu lô chỉ có tiêu đề.
        """
        if not any(e.text.strip() or e.table_data for e in elements if e.type.lower() != "heading"):
            return []
        return self.text_chunker.chunk(elements, document_id=document_id)


__all__ = ["MultimodalChunker"]
