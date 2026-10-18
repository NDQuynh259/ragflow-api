"""Pipeline xử lý và băm nhỏ tài liệu đa phương thức, thích ứng ngữ cảnh (Adaptive Multimodal Document Pipeline).

Package này cung cấp quy trình xử lý tài liệu hoàn chỉnh từ đầu đến cuối:
1. Phân tích cú pháp & bố cục (Parsing & Layout Analysis): Chuyển đổi PDF, Word, HTML sang LayoutElement.
2. Chuẩn hóa (Normalization): Chuẩn hóa Unicode NFC, sửa lỗi font (mojibake), gắn kết chú thích (caption/footnote).
3. Biểu diễn trung gian (Normalized Document IR): Xây dựng cấu trúc phân cấp tài liệu ổn định và có thể truy vết.
4. Phân loại 3 tầng (3-Tier Document Classification): Nhận diện loại văn bản (SOP, Hợp đồng, Báo cáo, Kế hoạch, Wiki).
5. Điều phối băm thích ứng (Adaptive Chunking Router): Áp dụng chiến lược tối ưu cho từng miền nghiệp vụ và loại phần tử.
6. Xác thực tính toàn vẹn (Integrity Validation): Kiểm tra độ phủ, kích thước token và báo cáo chẩn đoán.
"""

from .config import ChunkingConfig
from .models import (
    DocumentChunk,
    DocumentIR,
    ElementIR,
    ElementType,
    ImageData,
    LayoutElement,
    ProcessedDocument,
    SectionIR,
    SourceLocation,
    TableData,
)
from .pipeline import DocumentPipeline
from .validation import IntegrityReport

__all__ = [
    "ChunkingConfig",
    "DocumentChunk",
    "DocumentPipeline",
    "DocumentIR",
    "ElementIR",
    "SectionIR",
    "SourceLocation",
    "ElementType",
    "IntegrityReport",
    "ImageData",
    "LayoutElement",
    "ProcessedDocument",
    "TableData",
]
