"""Image/figure chunker orchestration strategy.

Lớp ImageChunker điều phối pipeline xử lý hình ảnh dựa trên các tiện ích
lõi (triage heuristics, Vision extraction, text proxy) trong
:mod:`rag_document_pipeline.chunking.core.image`.

Chiến lược hiện đại: Sử dụng trực tiếp mô hình thị giác AI (`vision_fn` - VLM) để
phân tích toàn diện hình ảnh (bao gồm đọc văn bản, mô tả nội dung, bóc tách số liệu biểu đồ).
"""

from __future__ import annotations

from rag_document_pipeline.models import DocumentChunk, LayoutElement

from ..core.image import (
    DEFAULT_MAX_ASPECT_RATIO,
    DEFAULT_MAX_VISION_LENGTH,
    DEFAULT_MIN_IMAGE_SIZE,
    IMAGE_PLACEHOLDER,
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


class ImageChunker:
    """Chiến lược băm hình ảnh/sơ đồ dựa trên phân tích thị giác AI (Vision VLM).

    Quy trình điều phối tuần tự:
    1. Image Triage: Kiểm tra kích thước hình học để lọc bỏ ảnh icon hoặc viền trang trí.
    2. Source Resolution: Tìm đường dẫn ảnh nội bộ hoặc URI lưu trữ đám mây.
    3. Vision AI Analysis: Gọi mô hình Vision VLM (`vision_fn`) để phân tích toàn diện hình ảnh
       (đọc chữ, giải thích sơ đồ, trích xuất dữ liệu biểu đồ).
    4. Text Proxy Assembly: Tổng hợp toàn bộ thông tin thành văn bản Markdown đại diện.
    5. Chunk Assembly: Đóng gói thành đối tượng `DocumentChunk` với cờ `indexable` chuẩn xác.
    """

    def __init__(
        self,
        *,
        vision_fn: ExtractFn | None = None,
        max_vision_length: int = DEFAULT_MAX_VISION_LENGTH,
        triage_enabled: bool = True,
        min_image_size: int = DEFAULT_MIN_IMAGE_SIZE,
        max_aspect_ratio: float = DEFAULT_MAX_ASPECT_RATIO,
    ) -> None:
        """Khởi tạo ImageChunker với callback Vision AI và cấu hình Triage.

        Args:
            vision_fn: Callback thực thi Vision AI phân tích ảnh/biểu đồ/văn bản (VLM).
            max_vision_length: Giới hạn ký tự tối đa cho kết quả trích xuất từ Vision AI.
            triage_enabled: Bật/tắt cơ chế lọc Triage hình học để tiết kiệm chi phí gọi API.
            min_image_size: Ngưỡng kích thước tối thiểu (px), nhỏ hơn sẽ bị đánh dấu trang trí.
            max_aspect_ratio: Ngưỡng tỷ lệ cạnh tối đa (width/height), lớn hơn sẽ bị coi là đường kẻ.
        """
        self.vision_fn = vision_fn
        self.max_vision_length = max_vision_length
        self.triage_enabled = triage_enabled
        self.min_image_size = min_image_size
        self.max_aspect_ratio = max_aspect_ratio

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

    def extract_text(self, element: LayoutElement) -> str | None:
        """Trích xuất text đại diện cho một phần tử ảnh (bước extraction, KHÔNG sinh chunk).

        Quy trình: Triage hình học -> giải quyết nguồn ảnh -> gọi Vision VLM (nếu có)
        -> ghép text proxy. Trả về None khi ảnh bị triage skip hoặc hoàn toàn không có
        nội dung text (không caption/description/vision) — ảnh đó không góp text
        vào dòng chunk chung.
        """
        skip_reason = triage_skip_reason(
            element,
            enabled=self.triage_enabled,
            min_image_size=self.min_image_size,
            max_aspect_ratio=self.max_aspect_ratio,
        )
        if skip_reason:
            return None

        img = element.image_data
        caption = (img.caption if img else None) or element.caption or ""
        description = img.description if img else None
        source = resolve_image_source(element)

        analysis: str | None = None
        if source and self.vision_fn:
            res = safe_extract_text(
                self.vision_fn,
                source,
                label="Vision",
                max_length=self.max_vision_length,
                element_id=element.id,
            )
            analysis = res.text
            if analysis and img:
                img.description = (res.structured_data or {}).get("main_message") or analysis

        content = build_image_text_proxy(
            element,
            caption=caption,
            description=description,
            analysis=analysis,
        )
        if content.strip() == IMAGE_PLACEHOLDER:
            return None
        return content

    def _build_skipped_chunk(
        self,
        element: LayoutElement,
        *,
        skip_reason: str,
        document_id: str,
        workspace_id: str = "",
    ) -> DocumentChunk:
        """Tạo chunk metadata cho ảnh bị loại bởi bộ lọc Triage (icon/kẻ trang trí).

        Chunk này có `indexable=False`, content là `[IMAGE]` và ghi rõ `triage_skip_reason`.
        Nhờ đó, bước sinh embedding sẽ bỏ qua 100%, không tốn chi phí vector embedding.
        """
        img = element.image_data
        metadata = image_metadata(img, image_available=bool(img and img.uri))
        metadata.update(
            triage_skipped=True,
            triage_skip_reason=skip_reason,
            index_reason=skip_reason,
        )
        return build_image_chunk(
            element,
            document_id=document_id,
            workspace_id=workspace_id,
            content=IMAGE_PLACEHOLDER,
            metadata=metadata,
            indexable=False,
        )

    def _chunk_image(
        self,
        element: LayoutElement,
        *,
        document_id: str,
        workspace_id: str = "",
    ) -> DocumentChunk:
        """Thực thi toàn bộ pipeline băm cho một phần tử hình ảnh đơn lẻ."""
        img = element.image_data

        # BƯỚC 1: Image Triage - Lọc bỏ ảnh rác/trang trí trước khi gọi Vision API
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

        # BƯỚC 2: Thu thập thông tin văn bản có sẵn & đường dẫn tệp ảnh
        caption = (img.caption if img else None) or element.caption or ""
        description = img.description if img else None
        source = resolve_image_source(element)

        # Khởi tạo metadata cơ bản cho chunk hợp lệ
        metadata = image_metadata(img, image_available=bool(source or (img and img.uri)))

        # BƯỚC 3: Phân tích hình ảnh toàn diện qua Vision AI (vision_fn)
        analysis: str | None = None
        if source and self.vision_fn:
            metadata["vision_attempted"] = True
            analysis = run_image_callback(
                self.vision_fn,
                source,
                element=element,
                metadata=metadata,
                label="Vision",
                max_length=self.max_vision_length,
            )
            if analysis:
                metadata["has_vision"] = True
                metadata["has_vision_analysis"] = True
                metadata["vision_text"] = analysis
                if img:
                    img.description = metadata.get("main_message") or analysis

        # BƯỚC 4: Tổng hợp chuỗi văn bản đại diện (Text Proxy)
        content = build_image_text_proxy(
            element,
            caption=caption,
            description=description,
            analysis=analysis,
        )

        # Ghi nhận lý do không thể index nếu hoàn toàn không có nội dung văn bản nào
        if not analysis and not description and not caption and content == IMAGE_PLACEHOLDER:
            metadata["index_reason"] = "no_caption_or_description"

        # BƯỚC 5: Đóng gói DocumentChunk hoàn chỉnh
        return build_image_chunk(
            element,
            document_id=document_id,
            workspace_id=workspace_id,
            content=content,
            metadata=metadata,
        )


__all__ = [
    "DEFAULT_MAX_ASPECT_RATIO",
    "DEFAULT_MAX_VISION_LENGTH",
    "DEFAULT_MIN_IMAGE_SIZE",
    "Dimensions",
    "ExtractFn",
    "ExtractionResult",
    "IMAGE_PLACEHOLDER",
    "ImageChunker",
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
