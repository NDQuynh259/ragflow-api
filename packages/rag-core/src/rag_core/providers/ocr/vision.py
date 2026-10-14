"""Gemini vision analysis provider for charts and diagrams."""

from __future__ import annotations

import logging
import os
from typing import Any, Literal

from pydantic import BaseModel, Field

from .gemini import GeminiOCR

logger = logging.getLogger(__name__)

#: Các loại hình ảnh được phép. Dùng Literal để ép model chọn đúng một giá trị,
#: tránh phân loại tự do gây lệch giữa các lần chạy.
ImageType = Literal[
    "Sơ đồ quy trình",
    "Biểu đồ cột",
    "Biểu đồ tròn",
    "Biểu đồ đường",
    "Bản vẽ kỹ thuật",
    "Tài liệu scan",
    "Bảng biểu",
    "Ảnh chụp minh họa",
    "Khác",
]

#: Mức độ tin cậy tổng thể của bản phân tích.
Confidence = Literal["high", "medium", "low"]


class ImageAnalysisResult(BaseModel):
    """Structured output schema for multimodal image analysis."""

    image_type: ImageType = Field(
        description=(
            "Loại hình của hình ảnh, chọn MỘT trong các giá trị: "
            "Sơ đồ quy trình / Biểu đồ cột / Biểu đồ tròn / Biểu đồ đường / "
            "Bản vẽ kỹ thuật / Tài liệu scan / Bảng biểu / Ảnh chụp minh họa / Khác"
        ),
    )
    title: str = Field(
        default="Không rõ",
        description="Tiêu đề hoặc chủ đề chính của ảnh. Nếu không rõ, ghi 'Không rõ'",
    )
    main_message: str = Field(
        default="Không rõ",
        description="Tóm tắt 1-2 câu về ý nghĩa, mục đích hoặc xu hướng chính của hình ảnh. Nếu không rõ, ghi 'Không rõ'",
    )
    detailed_data: list[str] = Field(
        default_factory=list,
        description=(
            "Danh sách các số liệu định lượng chi tiết hoặc từng nhánh, từng bước trong quy trình nhìn thấy trên ảnh. "
            "Mỗi số liệu phải kèm đơn vị đo và (nếu là biểu đồ) ghi rõ trục/thang đo. "
            "Do NOT invent numbers (Zero Hallucination). Nếu không có số liệu/dữ liệu rõ ràng thì trả về danh sách rỗng"
        ),
    )
    visible_text: list[str] = Field(
        default_factory=list,
        description=(
            "Danh sách tất cả các từ ngữ, câu chữ, nhãn tiếng Việt và tiếng Anh đọc được chính xác 100% trong ảnh. "
            "Trích xuất verbatim, giữ nguyên dấu tiếng Việt và thứ tự; không diễn đạt lại, không dịch, không gộp. "
            "Nếu không có chữ đọc được thì trả về danh sách rỗng"
        ),
    )
    confidence: Confidence = Field(
        default="medium",
        description=(
            "Độ tin cậy tổng thể của bản phân tích: "
            "'high' (ảnh rõ nét, đủ chi tiết), 'medium' (khá rõ, một số chi tiết mờ), "
            "'low' (ảnh mờ/nhiễu, nhiều phần không đọc được)"
        ),
    )

    def to_formatted_text(self) -> str:
        """Format the structured analysis into standard text proxy for RAG chunking."""
        image_type = self.image_type.strip() if self.image_type else "Không rõ"
        title = self.title.strip() if self.title else "Không rõ"
        main_message = self.main_message.strip() if self.main_message else "Không rõ"
        confidence_label = {
            "high": "Cao",
            "medium": "Trung bình",
            "low": "Thấp",
        }.get(self.confidence, "Trung bình")

        lines: list[str] = [
            "[IMAGE_ANALYSIS]",
            f"Loại hình: {image_type}",
            f"Tiêu đề & Chủ đề: {title}",
            f"Thông điệp chính: {main_message}",
            f"Độ tin cậy: {confidence_label}",
        ]
        if self.detailed_data:
            lines.append("Dữ liệu chi tiết & Nội dung:")
            for item in self.detailed_data:
                clean_item = item.strip()
                if clean_item:
                    lines.append(f"- {clean_item}")
        if self.visible_text:
            lines.append("Văn bản nhìn thấy:")
            for text in self.visible_text:
                clean_text = text.strip()
                if clean_text:
                    lines.append(f"- {clean_text}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Convert to standardized JSON dict with formatted_text proxy included."""
        data = self.model_dump()
        data["formatted_text"] = self.to_formatted_text()
        return data


VISION_ANALYSIS_PROMPT = """Phân tích hình ảnh này cho hệ thống RAG doanh nghiệp bằng tiếng Việt, trả về đúng schema JSON được yêu cầu.

Nguyên tắc chung:
- Chỉ mô tả những gì THỰC SỰ nhìn thấy trên ảnh. Không suy diễn, không bịa đặt, không suy luận ngoài ảnh.
- Zero Hallucination (Do NOT invent numbers): tuyệt đối không tự tạo, làm tròn, ước lượng hay nội suy số liệu. Nếu không đọc rõ, ghi "Không rõ" hoặc để danh sách rỗng.

Hướng dẫn từng trường:
- image_type: Loại hình - Chọn MỘT trong các giá trị: Sơ đồ quy trình / Biểu đồ cột / Biểu đồ tròn / Biểu đồ đường / Bản vẽ kỹ thuật / Tài liệu scan / Bảng biểu / Ảnh chụp minh họa / Khác.
- title: Tiêu đề hoặc chủ đề chính của ảnh. Nếu không rõ, ghi "Không rõ".
- main_message: Tóm tắt 1-2 câu về ý nghĩa, mục đích hoặc xu hướng chính của hình ảnh. Nếu không rõ, ghi "Không rõ".
- detailed_data: Dữ liệu chi tiết & Nội dung - Liệt kê từng nhánh/bước quy trình, mốc quan trọng, hoặc số liệu định lượng kèm ĐƠN VỊ ĐO. Với biểu đồ: đọc đúng trục (trục tung/trục hoành), thang đo và giá trị từng cột/điểm. Chỉ ghi những số đã nhìn thấy rõ.
- visible_text: Văn bản nhìn thấy - Trích xuất CHUẨN XÁC 100% (verbatim) tất cả từ ngữ, nhãn tiếng Việt và tiếng Anh đọc được, giữ nguyên dấu tiếng Việt và thứ tự. Không diễn đạt lại, không dịch, không gộp. Chỉ đưa vào những phần đọc chắc chắn.
- confidence: Độ tin cậy tổng thể của bản phân tích: "high" (ảnh rõ nét, đủ chi tiết), "medium" (khá rõ, một số chi tiết mờ), "low" (ảnh mờ/nhiễu, nhiều phần không đọc được).

Quy tắc nghiêm ngặt:
1. Không tự suy diễn hay bịa đặt số liệu (Zero Hallucination - Do NOT invent numbers). Nếu không rõ, ghi "Không rõ" hoặc để danh sách rỗng.
2. Chỉ mô tả những thông tin thực sự nhìn thấy trên ảnh.
3. Trước khi trả lời, tự kiểm tra lại: mỗi số liệu trong detailed_data và mỗi dòng trong visible_text có thực sự xuất hiện trên ảnh không? Nếu không chắc, bỏ đi."""

DEFAULT_VISION_PROMPT = VISION_ANALYSIS_PROMPT


class GeminiVisionAnalyzer:
    """Analyze charts and diagrams with a structured Gemini vision prompt and Pydantic schema."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 30.0,
        max_image_bytes: int | None = None,
        allow_private_network: bool = False,
        client: Any = None,
    ) -> None:
        self._model = model or os.environ.get("VISION_MODEL", "gemini-3.5-flash")
        self._reader: Any = GeminiOCR(
            api_key=api_key,
            model=self._model,
            timeout=timeout,
            max_image_bytes=max_image_bytes,
            allow_private_network=allow_private_network,
        )
        self._client: Any = client if client is not None else self._reader._client

    def _generate(self, image_source: str) -> str:
        """Read the image and return the raw model text, or an empty string on any failure."""
        import time

        try:
            image_bytes, mime_type = self._reader._read_image(image_source)
        except Exception as exc:
            logger.warning("Failed to read image %s: %s", image_source, exc)
            return ""

        from google.genai import types

        config = types.GenerateContentConfig(
            temperature=0,
            max_output_tokens=4096,
            response_mime_type="application/json",
            response_schema=ImageAnalysisResult,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

        models_to_try = [self._model]
        fallback = "gemini-3.1-flash-lite" if self._model != "gemini-3.1-flash-lite" else "gemini-3.5-flash"
        if fallback not in models_to_try:
            models_to_try.append(fallback)

        for model in models_to_try:
            for attempt in range(1, 3):
                try:
                    response = self._client.models.generate_content(
                        model=model,
                        contents=[
                            types.Part.from_text(text=VISION_ANALYSIS_PROMPT),
                            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                        ],
                        config=config,
                    )
                    return (response.text or "").strip()
                except Exception as exc:
                    err_str = str(exc)
                    is_transient = (
                        "503" in err_str
                        or "UNAVAILABLE" in err_str
                        or "429" in err_str
                        or "RESOURCE_EXHAUSTED" in err_str
                    )
                    if is_transient and attempt < 2:
                        logger.warning(
                            "Transient error on %s (attempt %d/2) for %s: %s. Retrying in 2s...",
                            model,
                            attempt,
                            image_source,
                            exc,
                        )
                        time.sleep(2)
                        continue
                    logger.warning(
                        "Gemini vision analysis failed on %s for %s: %s",
                        model,
                        image_source,
                        exc,
                    )
                    break
        return ""

    def analyze(self, image_source: str) -> ImageAnalysisResult | None:
        """Return validated ImageAnalysisResult, or None when analysis fails."""
        raw_text = self._generate(image_source)
        if not raw_text:
            return None
        try:
            return ImageAnalysisResult.model_validate_json(raw_text)
        except Exception as exc:
            logger.warning("Failed to parse vision analysis for %s: %s", image_source, exc)
            return None

    def analyze_dict(self, image_source: str) -> dict[str, Any] | None:
        """Return standardized JSON dict, or None when analysis fails."""
        raw_text = self._generate(image_source)
        if not raw_text:
            return None
        try:
            return ImageAnalysisResult.model_validate_json(raw_text).to_dict()
        except Exception as exc:
            logger.warning("Failed to parse vision analysis for %s: %s", image_source, exc)
            return {
                "image_type": "Khác",
                "title": "Không rõ",
                "main_message": "Không rõ",
                "detailed_data": [],
                "visible_text": [],
                "confidence": "low",
                "formatted_text": raw_text,
            }

    def analyze_text(self, image_source: str) -> str:
        """Return formatted Markdown text proxy for compatibility or manual inspection."""
        res = self.analyze_dict(image_source)
        if not res:
            return ""
        return res.get("formatted_text", "")

    def __call__(self, image_source: str) -> dict[str, Any] | None:
        """Return standardized JSON dict for RAG chunking, or None on failure."""
        return self.analyze_dict(image_source)


__all__ = [
    "DEFAULT_VISION_PROMPT",
    "GeminiVisionAnalyzer",
    "ImageAnalysisResult",
    "VISION_ANALYSIS_PROMPT",
]
