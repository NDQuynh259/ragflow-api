"""Mô-đun làm giàu ngữ cảnh và siêu dữ liệu cho chunk (Enrichment Helpers).

Cung cấp các tiện ích:
- `section_breadcrumb`: Tạo chuỗi đường dẫn phân cấp mục lục (breadcrumb).
- `preserve_metadata_provenance`: Ghi nhận siêu dữ liệu kèm nguồn gốc (provenance) và độ tin cậy.
- `add_bidirectional_relationship`: Thiết lập liên kết tham chiếu chéo 2 chiều giữa các chunk (ví dụ: text ↔ bảng/hình).
"""

from .context import section_breadcrumb
from .metadata import preserve_metadata_provenance
from .relationships import add_bidirectional_relationship

__all__ = [
    "add_bidirectional_relationship",
    "preserve_metadata_provenance",
    "section_breadcrumb",
]
