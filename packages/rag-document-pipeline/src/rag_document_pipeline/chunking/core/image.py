"""Core image processing utilities: triage heuristics, extraction, and proxy construction.

Mô-đun này chứa toàn bộ các tiện ích xử lý lõi (Core Processing) cho hình ảnh trong pipeline:
1. Triage Heuristics & Geometry: Tính toán kích thước, lọc bỏ ảnh rác/icon/đường kẻ trang trí.
2. Safe Extraction: Thực thi callback Vision AI an toàn, chống gián đoạn pipeline xử lý tài liệu.
3. Text Proxy & Chunk Builder: Tổng hợp nội dung văn bản đại diện và đóng gói thành DocumentChunk.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from core.uuid7 import uuid7_str

from rag_document_pipeline.models import DocumentChunk, ImageData, LayoutElement

from .constants import (
    DEFAULT_MAX_ASPECT_RATIO,
    DEFAULT_MAX_VISION_LENGTH,
    DEFAULT_MIN_IMAGE_SIZE,
    IMAGE_PLACEHOLDER,
)
from .utils import estimate_tokens

logger = logging.getLogger(__name__)

# ==============================================================================
# Kiểu dữ liệu rút gọn cho chữ ký hàm
# ==============================================================================

#: Kiểu hàm Callback Vision AI: nhận URI/đường dẫn ảnh, trả về văn bản trích xuất
ExtractFn = Callable[[str], Any]

#: Cặp (width, height) đã tính toán từ metadata hoặc bbox
Dimensions = tuple[float, float]


# ==============================================================================
# 1. Image Triage & Lọc hình học (Geometric Filtering)
# ==============================================================================


# region image_dimensions
def image_dimensions(element: LayoutElement) -> Dimensions | None:
    """Lấy kích thước (width, height) của ảnh, ưu tiên pixel thực từ metadata, fallback sang bbox.

    Args:
        element: Phần tử LayoutElement cần đọc kích thước.

    Returns:
        Cặp (width, height) dạng số thực, hoặc None nếu không thể xác định.
    """
    metadata = element.metadata
    width = metadata.get("width") or metadata.get("image_width")
    height = metadata.get("height") or metadata.get("image_height")
    try:
        if width and height:
            return float(width), float(height)
    except (TypeError, ValueError):
        logger.warning("Bỏ qua kích thước ảnh không hợp lệ trên phần tử %s", element.id)

    # Nếu metadata không có, tính từ bounding box (bbox: [x0, y0, x1, y1])
    if element.bbox:
        x0, y0, x1, y1 = element.bbox
        return abs(x1 - x0), abs(y1 - y0)
    return None


# region _resolved_dimensions
def _resolved_dimensions(
    element: LayoutElement,
    dimensions: Dimensions | None,
) -> Dimensions | None:
    """Tái sử dụng kích thước đã tính sẵn để tránh phân tích lại metadata nhiều lần.

    Args:
        element: Phần tử ảnh cần đọc kích thước khi chưa có giá trị cache.
        dimensions: Kích thước đã tính ở bước trước; None buộc phải đọc lại metadata/bbox.

    Returns:
        Cặp (width, height) được ưu tiên lấy từ `dimensions`.
    """
    return dimensions if dimensions is not None else image_dimensions(element)


# region triage_skip_reason
def triage_skip_reason(
    element: LayoutElement,
    *,
    enabled: bool = True,
    min_image_size: int = DEFAULT_MIN_IMAGE_SIZE,
    max_aspect_ratio: float = DEFAULT_MAX_ASPECT_RATIO,
    dimensions: Dimensions | None = None,
) -> str | None:
    """Kiểm tra điều kiện Image Triage để lọc bỏ ảnh rác hoặc ảnh trang trí.

    Quy tắc lọc:
    - Nếu kích thước <= 0: bỏ qua với lý do 'invalid_dimensions'.
    - Nếu width hoặc height < min_image_size (mặc định 100px): xem là icon/bullet ('too_small').
    - Nếu tỷ lệ khung hình > max_aspect_ratio (mặc định 10.0): xem là đường kẻ chia trang ('extreme_aspect_ratio').

    Args:
        element: Phần tử ảnh cần kiểm tra.
        enabled: Cờ bật/tắt bộ lọc Triage.
        min_image_size: Ngưỡng kích thước tối thiểu (px).
        max_aspect_ratio: Ngưỡng tỷ lệ cạnh tối đa.
        dimensions: Kích thước đã tính sẵn (tùy chọn).

    Returns:
        Chuỗi lý do bỏ qua ('too_small', 'extreme_aspect_ratio', 'invalid_dimensions'),
        hoặc None nếu ảnh hợp lệ cần giữ lại xử lý tiếp.
    """
    if not enabled:
        return None

    size = _resolved_dimensions(element, dimensions)
    if size is None:
        return None

    width, height = size
    if width <= 0 or height <= 0:
        return "invalid_dimensions"

    if width < min_image_size or height < min_image_size:
        return "too_small"

    if max(width / height, height / width) > max_aspect_ratio:
        return "extreme_aspect_ratio"

    return None


# ==============================================================================
# 2. Content Extraction (Trích xuất văn bản an toàn qua Vision AI)
# ==============================================================================


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    """Kết quả trích xuất an toàn từ callback Vision AI."""

    text: str | None = None
    error: str | None = None
    is_truncated: bool = False
    structured_data: dict[str, Any] | None = None


# region safe_extract_text
def safe_extract_text(
    callback: ExtractFn,
    source: str,
    *,
    label: str = "Vision",
    max_length: int = DEFAULT_MAX_VISION_LENGTH,
    element_id: str = "",
) -> ExtractionResult:
    """Thực thi callback Vision AI một cách an toàn mà không làm gián đoạn ingestion.

    Cơ chế bảo vệ:
    - Bắt mọi Exception từ callback ngoài, ghi log warning và trả về ExtractionResult(error=...).
    - Hỗ trợ đa dạng đầu ra: Python dict (JSON chuẩn), Pydantic Model, hoặc chuỗi ký tự (str).
    - Cắt ngắn (truncate) nếu văn bản vượt quá `max_length` để bảo vệ token limit của LLM.

    Args:
        callback: Hàm thực thi trích xuất (Vision callback).
        source: Đường dẫn tệp hoặc URI của hình ảnh.
        label: Tên nhãn mô tả ('Vision') để ghi log.
        max_length: Giới hạn ký tự tối đa cho kết quả trích xuất.
        element_id: Mã phần tử layout để đối soát log.

    Returns:
        Đối tượng ExtractionResult chứa văn bản, dữ liệu có cấu trúc, lỗi và cờ cắt ngắn.
    """
    try:
        extracted = callback(source)
    except Exception as exc:
        logger.warning("Trích xuất %s thất bại cho %s: %s", label, source, exc)
        return ExtractionResult(error=str(exc))

    if not extracted:
        return ExtractionResult()

    structured = extracted if isinstance(extracted, dict) else None
    text = extracted.get("formatted_text", "") if isinstance(extracted, dict) else str(extracted).strip()

    if len(text) > max_length:
        logger.warning("Văn bản %s cho phần tử %s vượt quá %d ký tự, đang cắt ngắn", label, element_id, max_length)
        return ExtractionResult(text=text[:max_length], is_truncated=True, structured_data=structured)

    return ExtractionResult(text=text, structured_data=structured)


# region run_image_callback
def run_image_callback(
    callback: ExtractFn,
    image_source: str,
    *,
    element: LayoutElement,
    metadata: dict[str, Any],
    label: str = "Vision",
    max_length: int = DEFAULT_MAX_VISION_LENGTH,
) -> str | None:
    """Chạy extraction và tự động ghi nhận error/truncated/structured data vào metadata của chunk."""
    prefix = label.lower()
    res = safe_extract_text(
        callback,
        image_source,
        label=label,
        max_length=max_length,
        element_id=element.id,
    )
    if res.error:
        metadata[f"{prefix}_error"] = res.error
    if res.is_truncated:
        metadata[f"{prefix}_truncated"] = True
    if res.structured_data:
        metadata.update(res.structured_data)
        if res.structured_data.get("title"):
            metadata["figure_title"] = res.structured_data["title"]
        metadata["vision_structured"] = res.structured_data
    return res.text


# region resolve_image_source
def resolve_image_source(element: LayoutElement) -> str | None:
    """Trích xuất URI hoặc đường dẫn tệp hình ảnh từ LayoutElement.

    Tìm kiếm theo thứ tự ưu tiên:
    1. element.image_data.uri
    2. element.source
    3. element.metadata['image_path']
    4. element.metadata['uri']

    Args:
        element: Phần tử ảnh cần xác định nguồn ảnh.

    Returns:
        Chuỗi URI/đường dẫn đầu tiên tìm thấy, hoặc None nếu phần tử không có nguồn ảnh.
    """
    img = element.image_data
    return (
        (img.uri if img else None)
        or element.source
        or element.metadata.get("image_path")
        or element.metadata.get("uri")
    )


# ==============================================================================
# 3. Text Proxy & Đóng gói DocumentChunk
# ==============================================================================


# region build_image_text_proxy
def build_image_text_proxy(
    element: LayoutElement,
    *,
    caption: str,
    description: str | None,
    analysis: str | None,
) -> str:
    """Ghép nối nội dung ngữ cảnh của ảnh thành chuỗi văn bản đại diện (Text Proxy).

    Cấu trúc chuỗi Text Proxy:
    - Bắt đầu bằng thẻ tag `[IMAGE]`.
    - Tiêu đề ảnh (Caption).
    - Mô tả ảnh (Description - nếu khác với analysis).
    - Phân tích Vision VLM (Analysis) nếu có.
    - Văn bản gốc trong element.text (nếu chưa trùng với các phần trên).
    - Chú thích cuối ảnh (Note: footnote).

    Args:
        element: Phần tử ảnh gốc.
        caption: Tiêu đề ảnh.
        description: Mô tả có sẵn của ảnh.
        analysis: Kết quả phân tích có cấu trúc từ mô hình Vision VLM.

    Returns:
        Chuỗi văn bản Markdown nhiều dòng đại diện cho ảnh.
    """
    parts: list[str] = [IMAGE_PLACEHOLDER]
    if caption:
        parts.append(caption)
    if description and description != analysis:
        parts.append(description)
    if analysis:
        parts.append(analysis)

    text = element.text.strip()
    if text and text not in parts:
        parts.append(text)

    footnote = element.metadata.get("footnote")
    if footnote:
        parts.append(f"Note: {footnote}")
    return "\n".join(parts)


# region image_metadata
def image_metadata(img: ImageData | None, *, image_available: bool) -> dict[str, Any]:
    """Tạo cấu trúc metadata cơ bản cho cả chunk đã index lẫn chunk bị triage skip.

    Args:
        img: Khối ImageData của phần tử (có thể None nếu parser không bóc được ảnh).
        image_available: Cờ cho biết luồng xử lý vẫn lấy được nguồn ảnh để trích xuất.
            Cờ này được truyền từ orchestration thay vì suy từ `img` vì nguồn ảnh vẫn có
            thể nằm ở `element.source` hoặc `metadata['image_path']` khi `img` vắng mặt.

    Returns:
        Dict metadata chứa `chunker`, `modality`, `image_available` và `image_uri` (nếu có).
    """
    metadata: dict[str, Any] = {
        "chunker": "image",
        "modality": "image",
        "image_available": image_available,
    }
    if img is not None and img.uri:
        metadata["image_uri"] = img.uri
    return metadata


# region build_image_chunk
def build_image_chunk(
    element: LayoutElement,
    *,
    document_id: str,
    workspace_id: str,
    content: str,
    metadata: dict[str, Any],
    indexable: bool | None = None,
) -> DocumentChunk:
    """Tạo đối tượng DocumentChunk hoàn chỉnh đại diện cho một hình ảnh hoặc sơ đồ.

    Quy tắc xác định cờ indexable:
    - Nếu tham số `indexable` được chỉ định rõ: dùng giá trị đó.
    - Mặc định: `indexable = True` khi content khác placeholder `[IMAGE]` và không bị triage skip.

    Args:
        element: Phần tử ảnh nguồn, cung cấp trang, bbox, section_path và element id.
        document_id: Mã tài liệu sở hữu chunk.
        workspace_id: Mã workspace để cô lập phạm vi truy vấn.
        content: Chuỗi text proxy đã ghép từ caption/vision analysis.
        metadata: Dict metadata đã hoàn thiện của chunk ảnh.
        indexable: Ghi đè cờ index; None để suy ra theo quy tắc mặc định ở trên.

    Returns:
        Đối tượng `DocumentChunk` với `kind='figure'` và `token_count` đã ước lượng.
    """
    has_meaningful_content = content != IMAGE_PLACEHOLDER
    is_indexable = (
        indexable
        if indexable is not None
        else (has_meaningful_content and not metadata.get("triage_skipped", False))
    )
    return DocumentChunk(
        id=uuid7_str(),
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


# Backward-compatibility aliases
image_source = resolve_image_source
image_text_proxy = build_image_text_proxy
make_image_chunk = build_image_chunk


__all__ = [
    "DEFAULT_MAX_ASPECT_RATIO",
    "DEFAULT_MAX_VISION_LENGTH",
    "DEFAULT_MIN_IMAGE_SIZE",
    "IMAGE_PLACEHOLDER",
    "Dimensions",
    "ExtractFn",
    "ExtractionResult",
    "build_image_chunk",
    "build_image_text_proxy",
    "image_dimensions",
    "image_metadata",
    "image_source",
    "image_text_proxy",
    "make_image_chunk",
    "resolve_image_source",
    "run_image_callback",
    "safe_extract_text",
    "triage_skip_reason",
]
