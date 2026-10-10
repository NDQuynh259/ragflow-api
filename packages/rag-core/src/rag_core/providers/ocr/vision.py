"""Gemini vision analysis provider for charts and diagrams."""

from __future__ import annotations

import logging
import os
from typing import Any

from .gemini import GeminiOCR

logger = logging.getLogger(__name__)

VISION_ANALYSIS_PROMPT = """[IMAGE_ANALYSIS]
Phân tích biểu đồ hoặc sơ đồ trong hình ảnh. Chỉ trả về các mục sau bằng tiếng Việt:

Loại hình: [biểu đồ cột, biểu đồ tròn, sơ đồ quy trình, sơ đồ tổ chức, hoặc loại phù hợp]
Tiêu đề: [tiêu đề, nhãn trục hoặc Không rõ]
Thông điệp chính: [xu hướng hoặc ý nghĩa chính, hoặc Không rõ]
Dữ liệu chi tiết:
- [liệt kê từng điểm dữ liệu nhìn thấy, kèm số liệu nếu có]
Văn bản nhìn thấy (OCR): [tất cả nhãn và văn bản đọc được, hoặc Không rõ]

Nếu dữ liệu không rõ, ghi "Không rõ". Do NOT invent numbers. Chỉ mô tả thông tin thực sự nhìn thấy trong hình ảnh."""


class GeminiVisionAnalyzer:
    """Analyze charts and diagrams with a structured Gemini vision prompt."""

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
        self._model = model or os.environ.get("VISION_MODEL", "gemini-2.0-flash")
        self._reader: Any = GeminiOCR(
            api_key=api_key,
            model=self._model,
            timeout=timeout,
            max_image_bytes=max_image_bytes,
            allow_private_network=allow_private_network,
        )
        self._client: Any = client if client is not None else self._reader._client

    def __call__(self, image_source: str) -> str:
        """Return structured analysis, or an empty string when unavailable."""
        try:
            image_bytes, mime_type = self._reader._read_image(image_source)
            from google.genai import types

            response = self._client.models.generate_content(
                model=self._model,
                contents=[
                    types.Part.from_text(text=VISION_ANALYSIS_PROMPT),
                    types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                ],
                config=types.GenerateContentConfig(
                    temperature=0,
                    max_output_tokens=4096,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                ),
            )
            return (response.text or "").strip()
        except Exception as exc:
            logger.warning("Gemini vision analysis failed for %s: %s", image_source, exc)
            return ""


__all__ = ["GeminiVisionAnalyzer", "VISION_ANALYSIS_PROMPT"]
