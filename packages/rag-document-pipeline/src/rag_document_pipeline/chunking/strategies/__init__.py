"""Chunking strategies for different content types (Modality Strategies).

Gói này cài đặt Strategy Pattern cho từng loại nội dung chuyên biệt trong tài liệu:
- `TextChunker`: Chiến lược băm văn bản lai (Hybrid Semantic Chunking) dựa trên cấu trúc
  chương mục và phát hiện điểm đổi ý (Topic Shifts) qua khoảng cách ngữ nghĩa.
- `TableChunker`: Chiến lược băm bảng biểu bảo toàn cấu trúc Markdown Table,
  cắt sliding window theo dòng và sinh `searchable_text` (Header = Value) tối ưu cho retrieval.
- `ImageChunker`: Chiến lược băm hình ảnh/sơ đồ, tích hợp Image Triage (lọc rác)
  và mô hình Vision VLM phân tích toàn diện cấu trúc, số liệu, văn bản.
"""

from .image import ImageChunker
from .table import TableChunker
from .text import TextChunker

__all__ = [
    "ImageChunker",
    "TableChunker",
    "TextChunker",
]
