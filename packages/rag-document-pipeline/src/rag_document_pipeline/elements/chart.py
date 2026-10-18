"""Bộ xử lý phần tử biểu đồ (Chart Processor).

Định tuyến các phần tử biểu đồ (chart) thông qua quy trình xử lý hình ảnh thị giác (VLM / figure path)
mà không tự ý chế tạo dữ liệu cấu trúc giả lập.
"""

from __future__ import annotations

from rag_document_pipeline.chunking.strategies.image import ImageChunker
from rag_document_pipeline.models import DocumentChunk, LayoutElement


class ChartProcessor:
    """Xử lý phần tử biểu đồ bằng cách tận dụng năng lực phân tích hình ảnh (ImageChunker)."""

    def __init__(self, figure_processor: ImageChunker | None = None) -> None:
        """Khởi tạo ChartProcessor.

        Args:
            figure_processor: Bộ phân đoạn hình ảnh (ImageChunker). Nếu None, dùng mặc định.
        """
        self.figure_processor = figure_processor or ImageChunker()

    def chunk(self, element: LayoutElement, *, document_id: str) -> list[DocumentChunk]:
        """Băm nhỏ phần tử biểu đồ thành chunk hình ảnh độc lập kèm mô tả thị giác (nếu có).

        Args:
            element: Phần tử LayoutElement có kiểu là 'chart'.
            document_id: Mã định danh tài liệu.

        Returns:
            list[DocumentChunk]: Danh sách các chunk tương ứng với biểu đồ.
        """
        if element.type.lower() != "chart":
            raise ValueError("ChartProcessor requires an element of type 'chart'")
        return self.figure_processor.chunk([element], document_id=document_id)


__all__ = ["ChartProcessor"]
