"""Định nghĩa mô hình dữ liệu (Data Models) và hợp đồng miền (Domain Contracts) cho pipeline.

Mô-đun này tái xuất (re-export) các mô hình nền tảng từ `rag_contracts` để duy trì tính tương thích
ngược, đồng thời định nghĩa mô hình kết quả đầu ra chuẩn hóa `ProcessedDocument`.
"""

from __future__ import annotations

from pydantic import BaseModel

# Tái xuất (re-export) các hợp đồng miền dùng chung từ rag_contracts để tương thích ngược
from rag_contracts import (
    DocumentChunk,
    DocumentIR,
    ElementIR,
    ElementType,
    ImageData,
    LayoutElement,
    SectionIR,
    SourceLocation,
    TableData,
)
from rag_document_pipeline.validation import IntegrityReport

# ---------------------------------------------------------------------------
# Kết quả đầu ra của Document Pipeline
# ---------------------------------------------------------------------------


class ProcessedDocument(BaseModel):
    """Kết quả đầu ra hoàn chỉnh sau khi xử lý qua toàn bộ Document Pipeline.

    Bao gồm toàn bộ các phần tử bố cục (layout elements) đã qua chuẩn hóa,
    danh sách các chunk hoàn chỉnh sẵn sàng cho việc embedding/indexing,
    và báo cáo chẩn đoán tính toàn vẹn (integrity report).

    Attributes:
        document_id: Mã định danh duy nhất của tài liệu.
        filename: Tên tệp tin gốc của tài liệu.
        page_count: Tổng số trang tài liệu được phân tích.
        elements: Danh sách các phần tử bố cục (LayoutElement) đã được chuẩn hóa.
        chunks: Danh sách các chunk tài liệu (DocumentChunk) hoàn chỉnh sau phân đoạn.
        integrity_report: Báo cáo kiểm định tính toàn vẹn và độ bao phủ của chunking (nếu có).
    """

    document_id: str
    filename: str
    page_count: int
    elements: list[LayoutElement]
    chunks: list[DocumentChunk]
    integrity_report: IntegrityReport | None = None


__all__ = [
    "ElementType",
    "TableData",
    "ImageData",
    "LayoutElement",
    "DocumentChunk",
    "DocumentIR",
    "ElementIR",
    "IntegrityReport",
    "ProcessedDocument",
    "SectionIR",
    "SourceLocation",
]
