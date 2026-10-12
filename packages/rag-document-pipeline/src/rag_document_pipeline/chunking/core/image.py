"""Core image processing utilities: triage heuristics, extraction, and proxy construction.

Chứa toàn bộ các xử lý lõi (core processing) cho hình ảnh:
1. Triage Heuristics & Geometry: Tính toán kích thước, lọc ảnh rác/icon, phát hiện sơ đồ ngữ nghĩa.
2. Safe Extraction: Thực thi callback OCR/Vision an toàn không làm crash ingestion pipeline.
3. Text Proxy & Chunk Builder: Tổng hợp nội dung ngữ cảnh và đóng gói DocumentChunk.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Final

from rag_document_pipeline.chunking.core.utils import estimate_tokens
from rag_document_pipeline.models import DocumentChunk, LayoutElement

logger = logging.getLogger(__name__)

# --- Triage & Geometry Constants ---
#: Kích thước tối thiểu (px/pt), nhỏ hơn ngưỡng này xem là icon/ảnh trang trí
DEFAULT_MIN_IMAGE_SIZE: Final[int] = 100
#: Tỷ lệ cạnh tối đa (width/height), lớn hơn ngưỡng này xem là đường kẻ/viền
DEFAULT_MAX_ASPECT_RATIO: Final[float] = 10.0
#: Kích thước tối thiểu để kích hoạt Vision AI cho biểu đồ/sơ đồ
DEFAULT_VISION_MIN_SIZE: Final[int] = 400
#: Ngưỡng ký tự OCR tối đa để coi một ảnh lớn là biểu đồ (nhiều hình vẽ, ít chữ)
DEFAULT_VISION_MAX_TEXT: Final[int] = 80


# ==============================================================================
# 1. Image Triage & Geometric Filtering
# ==============================================================================


def image_dimensions(element: LayoutElement) -> tuple[float, float] | None:
    """Lấy kích thước (width, height) của ảnh, ưu tiên pixel thực từ metadata, fallback sang bbox."""
    width = element.metadata.get("width") or element.metadata.get("image_width")
    height = element.metadata.get("height") or element.metadata.get("image_height")
    try:
        if width and height:
            return float(width), float(height)
    except (TypeError, ValueError):
        logger.warning("Ignoring non-numeric image dimensions on element %s", element.id)

    if element.bbox:
        x0, y0, x1, y1 = element.bbox
        return abs(x1 - x0), abs(y1 - y0)
    return None


def triage_skip_reason(
    element: LayoutElement,
    *,
    enabled: bool = True,
    min_image_size: int = DEFAULT_MIN_IMAGE_SIZE,
    max_aspect_ratio: float = DEFAULT_MAX_ASPECT_RATIO,
) -> str | None:
    """Kiểm tra điều kiện Image Triage để lọc bỏ ảnh rác/trang trí.

    Returns:
        - Lý do bỏ qua ('too_small', 'extreme_aspect_ratio', 'invalid_dimensions')
        - None: Nếu ảnh hợp lệ cần giữ lại xử lý tiếp.
    """
    if not enabled:
        return None

    dimensions = image_dimensions(element)
    if dimensions is None:
        return None

    width, height = dimensions
    if width <= 0 or height <= 0:
        return "invalid_dimensions"

    if width < min_image_size or height < min_image_size:
        return "too_small"

    aspect_ratio = max(width / height, height / width)
    if aspect_ratio > max_aspect_ratio:
        return "extreme_aspect_ratio"

    return None


def is_semantic_figure(
    element: LayoutElement,
    ocr_text: str | None,
    *,
    vision_enabled: bool,
    vision_min_size: int = DEFAULT_VISION_MIN_SIZE,
    vision_max_text: int = DEFAULT_VISION_MAX_TEXT,
) -> bool:
    """Nhận diện xem ảnh có phải là biểu đồ/sơ đồ ngữ nghĩa cần gọi VLM Vision hay không.

    Heuristic: Ảnh có kích thước lớn (>= vision_min_size) nhưng chứa ít chữ OCR (< vision_max_text).
    """
    if not vision_enabled:
        return False

    dimensions = image_dimensions(element)
    if dimensions is None:
        return False

    if max(dimensions) < vision_min_size:
        return False

    return len((ocr_text or "").strip()) < vision_max_text


# ==============================================================================
# 2. Content Extraction & Formatting
# ==============================================================================


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    """Kết quả trích xuất an toàn từ OCR hoặc Vision callback."""

    text: str | None = None
    error: str | None = None
    is_truncated: bool = False


def safe_extract_text(
    callback: Any,
    source: str,
    *,
    label: str,
    max_length: int,
    element_id: str = "",
) -> ExtractionResult:
    """Thực thi callback (OCR/Vision) một cách an toàn mà không làm gián đoạn ingestion."""
    try:
        extracted = callback(source)
    except Exception as exc:
        logger.warning("%s extraction failed for %s: %s", label, source, exc)
        return ExtractionResult(error=str(exc))

    if not extracted or not isinstance(extracted, str) or not extracted.strip():
        return ExtractionResult()

    text = extracted.strip()
    is_truncated = False
    if len(text) > max_length:
        logger.warning(
            "%s text for element %s exceeds max length (%d), truncating",
            label,
            element_id,
            max_length,
        )
        text = text[:max_length]
        is_truncated = True

    return ExtractionResult(text=text, is_truncated=is_truncated)


def resolve_image_source(element: LayoutElement) -> str | None:
    """Trích xuất URI hoặc đường dẫn tệp của ảnh từ LayoutElement."""
    img = element.image_data
    return (
        (img.uri if img else None)
        or element.source
        or element.metadata.get("image_path")
        or element.metadata.get("uri")
    )


def build_image_text_proxy(
    element: LayoutElement,
    *,
    caption: str,
    description: str | None,
    analysis: str | None,
    ocr_text: str | None,
) -> str:
    """Ghép nối nội dung ngữ cảnh của ảnh thành chuỗi text đại diện (text proxy)."""
    parts = ["[IMAGE]"]
    if caption:
        parts.append(caption)
    if description and description != analysis:
        parts.append(description)
    if analysis:
        parts.append(analysis)
    elif ocr_text:
        parts.append(f"OCR: {ocr_text}" if not ocr_text.lower().startswith("ocr:") else ocr_text)
    if element.text.strip() and element.text.strip() not in parts:
        parts.append(element.text.strip())
    footnote = element.metadata.get("footnote")
    if footnote:
        parts.append(f"Note: {footnote}")
    return "\n".join(parts)


def image_metadata(element: LayoutElement) -> dict[str, Any]:
    """Metadata nền cho mọi image chunk: loại chunker, modality, URI ảnh."""
    img = element.image_data
    metadata: dict[str, Any] = {
        "chunker": "image",
        "modality": "image",
        "image_available": bool(img and img.uri),
    }
    if img and img.uri:
        metadata["image_uri"] = img.uri
    return metadata


def build_image_chunk(
    element: LayoutElement,
    *,
    document_id: str,
    workspace_id: str,
    content: str,
    metadata: dict[str, Any],
    indexable: bool | None = None,
) -> DocumentChunk:
    """Tạo DocumentChunk đại diện cho một ảnh/figure."""
    has_meaningful_content = content != "[IMAGE]"
    is_indexable = (
        indexable
        if indexable is not None
        else (has_meaningful_content and not metadata.get("triage_skipped", False))
    )
    return DocumentChunk(
        id=str(uuid.uuid4()),
        document_id=document_id,
        workspace_id=workspace_id,
        content=content,
        index=0,
        page_start=element.page_number,
        page_end=element.page_number,
        element_ids=[element.id],
        bboxes=[element.bbox] if element.bbox else [],
        kind="figure",
        section_path=element.section_path,
        token_count=estimate_tokens(content) if has_meaningful_content else 0,
        indexable=is_indexable,
        metadata=metadata,
    )


__all__ = [
    "DEFAULT_MAX_ASPECT_RATIO",
    "DEFAULT_MIN_IMAGE_SIZE",
    "DEFAULT_VISION_MAX_TEXT",
    "DEFAULT_VISION_MIN_SIZE",
    "ExtractionResult",
    "build_image_chunk",
    "build_image_text_proxy",
    "image_dimensions",
    "image_metadata",
    "is_semantic_figure",
    "resolve_image_source",
    "safe_extract_text",
    "triage_skip_reason",
]
