"""Image/figure chunker orchestration strategy.

Lớp ImageChunker điều phối pipeline xử lý hình ảnh dựa trên các tiện ích
lõi (triage heuristics, OCR/Vision extraction, text proxy) trong
:mod:`rag_document_pipeline.chunking.core.image`.
"""

from __future__ import annotations

from typing import Any, Final

from rag_document_pipeline.chunking.core.image import (
    DEFAULT_MAX_ASPECT_RATIO,
    DEFAULT_MIN_IMAGE_SIZE,
    DEFAULT_VISION_MAX_TEXT,
    DEFAULT_VISION_MIN_SIZE,
    build_image_chunk,
    build_image_text_proxy,
    image_metadata,
    is_semantic_figure,
    resolve_image_source,
    safe_extract_text,
    triage_skip_reason,
)
from rag_document_pipeline.models import DocumentChunk, LayoutElement

DEFAULT_MAX_OCR_LENGTH: Final[int] = 2000


class ImageChunker:
    """Chunk image/figure elements based on available textual context and visual analysis."""

    def __init__(
        self,
        *,
        ocr_fn: Any = None,
        vision_fn: Any = None,
        max_ocr_length: int = DEFAULT_MAX_OCR_LENGTH,
        triage_enabled: bool = True,
        min_image_size: int = DEFAULT_MIN_IMAGE_SIZE,
        max_aspect_ratio: float = DEFAULT_MAX_ASPECT_RATIO,
        vision_min_size: int = DEFAULT_VISION_MIN_SIZE,
        vision_max_text: int = DEFAULT_VISION_MAX_TEXT,
    ) -> None:
        self.ocr_fn = ocr_fn
        self.vision_fn = vision_fn
        self.max_ocr_length = max_ocr_length
        self.triage_enabled = triage_enabled
        self.min_image_size = min_image_size
        self.max_aspect_ratio = max_aspect_ratio
        self.vision_min_size = vision_min_size
        self.vision_max_text = vision_max_text

    def chunk(
        self,
        elements: list[LayoutElement],
        *,
        document_id: str,
        workspace_id: str = "",
    ) -> list[DocumentChunk]:
        """Chuyển đổi danh sách LayoutElement hình ảnh thành các DocumentChunk độc lập."""
        return [
            self._chunk_image(element, document_id=document_id, workspace_id=workspace_id)
            for element in elements
        ]

    def _build_skipped_chunk(
        self,
        element: LayoutElement,
        *,
        skip_reason: str,
        document_id: str,
        workspace_id: str = "",
    ) -> DocumentChunk:
        """Tạo chunk cho ảnh bị triage skip (trang trí / icon / divider)."""
        metadata = image_metadata(element)
        metadata["triage_skipped"] = True
        metadata["triage_skip_reason"] = skip_reason

        return build_image_chunk(
            element,
            document_id=document_id,
            workspace_id=workspace_id,
            content="[IMAGE]",
            metadata=metadata,
        )

    def _chunk_image(
        self,
        element: LayoutElement,
        *,
        document_id: str,
        workspace_id: str = "",
    ) -> DocumentChunk:
        # 1. Image Triage: Lọc ảnh rác theo hình học
        skip_reason = triage_skip_reason(
            element,
            enabled=self.triage_enabled,
            min_image_size=self.min_image_size,
            max_aspect_ratio=self.max_aspect_ratio,
        )
        if skip_reason:
            return self._build_skipped_chunk(
                element,
                skip_reason=skip_reason,
                document_id=document_id,
                workspace_id=workspace_id,
            )

        img = element.image_data
        caption = (img.caption if img else None) or element.caption or ""
        description = img.description if img else None
        ocr_text = (
            (img.ocr_text if img else None)
            or element.metadata.get("ocr_text")
            or element.metadata.get("ocr")
        )
        source = resolve_image_source(element)

        metadata = image_metadata(element)

        # 2. OCR Extraction: Trích xuất chữ khi chưa có OCR sẵn
        if self.ocr_fn:
            metadata["ocr_attempted"] = False

        if not ocr_text and self.ocr_fn and source:
            metadata["ocr_attempted"] = True
            ocr_res = safe_extract_text(
                self.ocr_fn,
                source,
                label="OCR",
                max_length=self.max_ocr_length,
                element_id=element.id,
            )
            if ocr_res.error:
                metadata["ocr_error"] = ocr_res.error
            if ocr_res.is_truncated:
                metadata["ocr_truncated"] = True
            if ocr_res.text:
                ocr_text = ocr_res.text
                element.metadata["ocr_text"] = ocr_text
                if img:
                    img.ocr_text = ocr_text

        if ocr_text:
            metadata["has_ocr"] = True
            metadata["ocr_text"] = ocr_text

        # 3. Vision Analysis: Phân tích biểu đồ/sơ đồ ngữ nghĩa ít chữ
        analysis: str | None = None
        if source and is_semantic_figure(
            element,
            ocr_text,
            vision_enabled=self.vision_fn is not None,
            vision_min_size=self.vision_min_size,
            vision_max_text=self.vision_max_text,
        ):
            metadata["vision_attempted"] = True
            vision_res = safe_extract_text(
                self.vision_fn,
                source,
                label="Vision",
                max_length=self.max_ocr_length,
                element_id=element.id,
            )
            if vision_res.error:
                metadata["vision_error"] = vision_res.error
            if vision_res.is_truncated:
                metadata["vision_truncated"] = True
            if vision_res.text:
                analysis = vision_res.text
                metadata["has_vision"] = True
                metadata["has_vision_analysis"] = True
                metadata["vision_text"] = analysis
                if img:
                    img.description = analysis

        # 4. Ghép nối Text Proxy
        content = build_image_text_proxy(
            element,
            caption=caption,
            description=description,
            analysis=analysis,
            ocr_text=ocr_text,
        )

        # 5. Fallback index_reason nếu không có text
        if not analysis and not ocr_text and content == "[IMAGE]":
            metadata["index_reason"] = "no_caption_or_description"

        # 6. Đóng gói DocumentChunk
        return build_image_chunk(
            element,
            document_id=document_id,
            workspace_id=workspace_id,
            content=content,
            metadata=metadata,
        )


__all__ = [
    "DEFAULT_MAX_OCR_LENGTH",
    "ImageChunker",
]
