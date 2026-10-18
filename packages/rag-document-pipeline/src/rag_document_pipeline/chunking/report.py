"""Chính sách phân đoạn báo cáo tiến độ và báo cáo định kỳ (Report Policy).

Hỗ trợ nhận diện các mốc kỳ báo cáo (Quý 1, Q1, Sprint 12, FY 2024, Tháng 10, Tuần 4...)
để không ngắt cụt hay gộp lẫn dữ liệu giữa hai kỳ báo cáo khác nhau.
"""

from __future__ import annotations

import re

from rag_document_pipeline.models import LayoutElement

# Mẫu regex nhận diện các mốc thời gian kỳ báo cáo
_PERIOD_RE = re.compile(
    r"(?i)\b(Q[1-4](?:\s*[-/]\s*\d{4})?|Sprint\s*\d+|FY\s*\d{4}|"
    r"tháng\s*\d{1,2}(?:/\d{4})?|tuần\s*\d+)\b"
)


class ReportPolicy:
    """Bảo toàn tính nguyên vẹn theo kỳ báo cáo và tránh cắt gộp qua tiêu đề kỳ."""

    @staticmethod
    def period(element: LayoutElement) -> str | None:
        """Trích xuất chuỗi định danh kỳ báo cáo từ phần tử (ví dụ: 'Q3 2024', 'Sprint 5').

        Args:
            element: Phần tử LayoutElement.

        Returns:
            str | None: Chuỗi kỳ báo cáo nếu khớp, hoặc None.
        """
        match = _PERIOD_RE.search(element.text)
        return match.group(1).strip() if match else None

    @classmethod
    def starts_period(cls, element: LayoutElement) -> bool:
        """Kiểm tra phần tử có phải là tiêu đề bắt đầu một kỳ báo cáo mới hay không."""
        return element.type.lower() == "heading" and cls.period(element) is not None


__all__ = ["ReportPolicy"]
