"""Hằng số dùng chung cho toàn bộ package chunking.

Nơi duy nhất khai báo các ngưỡng và tập hợp loại phần tử mà nhiều module cùng
dùng. Chỉ chứa hằng số thuần túy, không import từ module khác trong package để
tránh vòng lặp khi ``core`` được ``strategies`` nạp trước.

Quy tắc: hằng số chỉ một chiến lược dùng thì nằm lại module của chiến lược đó;
hằng số chia sẻ giữa nhiều module được gom vào tệp này.
"""

from __future__ import annotations

import re
from typing import Final

# ==============================================================================
# Ảnh & Hình học (Image Triage)
# ==============================================================================

#: Thẻ đánh dấu mở đầu mọi text proxy của ảnh; đồng thời là nội dung khi ảnh không có văn bản
IMAGE_PLACEHOLDER: Final[str] = "[IMAGE]"

#: Kích thước tối thiểu (px/pt), nhỏ hơn ngưỡng này được xem là icon hoặc ảnh trang trí
DEFAULT_MIN_IMAGE_SIZE: Final[int] = 100

#: Tỷ lệ cạnh tối đa (width/height hoặc height/width), vượt ngưỡng này được xem là đường kẻ/viền
DEFAULT_MAX_ASPECT_RATIO: Final[float] = 10.0

#: Giới hạn ký tự tối đa cho kết quả trích xuất văn bản từ mô hình Vision cho một ảnh
DEFAULT_MAX_VISION_LENGTH: Final[int] = 2000

# ==============================================================================
# Định tuyến theo loại phần tử (Multimodal Routing)
# ==============================================================================

#: Tập hợp các loại phần tử thuộc luồng văn bản thông thường
TEXT_TYPES = {"text", "heading", "paragraph", "list", "caption", "formula"}

#: Tập hợp các loại phần tử dạng bảng biểu
TABLE_TYPES = {"table", "data_table"}

#: Tập hợp các loại phần tử dạng hình ảnh, sơ đồ, biểu đồ
IMAGE_TYPES = {"image", "figure", "chart"}

#: Tập hợp các phần tử trang trí cần bỏ qua trong luồng nội dung chính (header/footer trang)
SKIP_TYPES = {"header", "footer"}

# ==============================================================================
# Tách câu an toàn cho tiếng Việt (Text Splitting)
# ==============================================================================

#: Ký tự mặt nạ tạm thời (Private Use Area Unicode) dùng để bảo vệ dấu chấm trong từ viết tắt/số thập phân
MASK_CHAR = "\ue000"

#: Biểu thức chính quy phát hiện các từ viết tắt phổ biến trong tiếng Việt và tiếng Anh
ABBREV_PATTERN = re.compile(
    r"\b(ThS|TS|GS|PGS|BS|DS|KTS|TP|đ/c|đ/v|v\.v|NĐ-CP|QĐ|TT|e\.g|i\.e|etc|Mr|Mrs|Dr|Ms|Prof)\."
)

#: Biểu thức chính quy phát hiện số thập phân có dấu chấm (ví dụ: 1.5, 100.000)
DECIMAL_PATTERN = re.compile(r"(\d)\.(\d)")


__all__ = [
    "ABBREV_PATTERN",
    "DECIMAL_PATTERN",
    "DEFAULT_MAX_ASPECT_RATIO",
    "DEFAULT_MAX_VISION_LENGTH",
    "DEFAULT_MIN_IMAGE_SIZE",
    "IMAGE_PLACEHOLDER",
    "IMAGE_TYPES",
    "MASK_CHAR",
    "SKIP_TYPES",
    "TABLE_TYPES",
    "TEXT_TYPES",
]
