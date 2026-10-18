"""Chính sách phân đoạn quy trình thao tác chuẩn và hướng dẫn (Procedure / SOP Policy).

Hỗ trợ nhận diện các bước thao tác tuần tự (Bước 1, Step 2...) để không cắt ngang một bước thực hiện,
đồng thời phát hiện và phân loại mức độ cảnh báo (warning level: warning, caution).
"""

from __future__ import annotations

import re

from rag_document_pipeline.models import LayoutElement

# Mẫu regex nhận diện các bước quy trình thao tác
_STEP_RE = re.compile(r"(?i)\b(?:bước|step)\s*\d+\b")


class ProcedurePolicy:
    """Bảo toàn ranh giới các bước quy trình (SOP steps) và phân loại cảnh báo."""

    @staticmethod
    def starts_step(element: LayoutElement) -> bool:
        """Kiểm tra phần tử có phải là tiêu đề đánh dấu bước thực hiện mới hay không."""
        return element.type.lower() == "heading" and bool(_STEP_RE.search(element.text))

    @staticmethod
    def warning_level(text: str) -> str | None:
        """Phân loại mức độ cảnh báo an toàn từ chuỗi văn bản.

        Args:
            text: Nội dung văn bản cần kiểm tra.

        Returns:
            str | None: 'warning' nếu có từ khóa nguy hiểm, 'caution' nếu có từ khóa lưu ý, hoặc None.
        """
        if re.search(r"(?i)\b(cảnh báo|nguy hiểm|warning|danger)\b", text):
            return "warning"
        if re.search(r"(?i)\b(lưu ý|chú ý|cẩn thận|caution|note)\b", text):
            return "caution"
        return None


__all__ = ["ProcedurePolicy"]
