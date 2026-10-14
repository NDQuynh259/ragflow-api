"""Facade của package chunking: Public surface cho toàn bộ hệ thống băm nhỏ tài liệu.

Module này cung cấp các điểm truy cập chính (Public API) cho ứng dụng bên ngoài và pipeline:
- `MultimodalChunker`: Bộ điều phối băm nhỏ toàn diện theo thứ tự đọc (Reading-order Router).
  Tự động định tuyến văn bản, bảng biểu và hình ảnh đến từng chiến lược tương ứng.
- `TextChunker`: Chiến lược băm văn bản dựa trên phân đoạn ngữ nghĩa (Topic Shifts).
- `TableChunker`: Chiến lược băm bảng biểu bảo toàn cấu trúc Markdown Table.
- `ImageChunker`: Chiến lược băm hình ảnh kết hợp Triage kích thước và mô hình thị giác Vision AI (VLM).
- `Chunker`: Giao diện (Protocol) chuẩn cho mọi bộ băm tài liệu.

Các helper nội bộ (metrics, section propagation, image pure helpers) nằm trong
:mod:`rag_document_pipeline.chunking.core` và chỉ nên được import trực tiếp khi cần thiết.
"""

from .core import Chunker
from .multimodal import MultimodalChunker
from .strategies import ImageChunker, TableChunker, TextChunker

__all__ = [
    "Chunker",
    "ImageChunker",
    "MultimodalChunker",
    "TableChunker",
    "TextChunker",
]
