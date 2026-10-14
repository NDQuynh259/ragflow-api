"""Chunking infrastructure: protocol, geometry/triage helpers, sections, metrics.

Hạ tầng dùng chung cho mọi chiến lược băm (Chunking Strategy):
- `base`: Giao diện `Chunker` Protocol.
- `section`: Lan truyền cây phân cấp tiêu đề (`propagate_sections`) và gom nhóm theo luồng đọc (`group_by_section`).
- `utils`: Tiện ích đo khoảng cách (`cosine_distance`, `jaccard_distance`) và ước lượng token (`estimate_tokens`).
- `constants`: Toàn bộ hằng số chia sẻ của package.
- `image`: Các pure helpers xử lý hình học ảnh, lọc triage, trích xuất text proxy và đóng gói chunk.
"""

from .base import Chunker
from .constants import (
    DEFAULT_MAX_ASPECT_RATIO,
    DEFAULT_MAX_VISION_LENGTH,
    DEFAULT_MIN_IMAGE_SIZE,
    IMAGE_PLACEHOLDER,
)
from .image import (
    Dimensions,
    ExtractFn,
    ExtractionResult,
    build_image_chunk,
    build_image_text_proxy,
    image_dimensions,
    image_metadata,
    image_source,
    image_text_proxy,
    make_image_chunk,
    resolve_image_source,
    run_image_callback,
    safe_extract_text,
    triage_skip_reason,
)
from .section import group_by_section, propagate_sections
from .utils import cosine_distance, estimate_tokens, jaccard_distance

__all__ = [
    "Chunker",
    "DEFAULT_MAX_ASPECT_RATIO",
    "DEFAULT_MAX_VISION_LENGTH",
    "DEFAULT_MIN_IMAGE_SIZE",
    "Dimensions",
    "ExtractFn",
    "ExtractionResult",
    "IMAGE_PLACEHOLDER",
    "build_image_chunk",
    "build_image_text_proxy",
    "cosine_distance",
    "estimate_tokens",
    "group_by_section",
    "image_dimensions",
    "image_metadata",
    "image_source",
    "image_text_proxy",
    "jaccard_distance",
    "make_image_chunk",
    "propagate_sections",
    "resolve_image_source",
    "run_image_callback",
    "safe_extract_text",
    "triage_skip_reason",
]
