"""Chính sách phân đoạn kế hoạch kinh doanh và tài chính (Business Plan Policy).

Hỗ trợ nhận diện ranh giới giữa các kịch bản dự báo (Kịch bản cơ sở, Kịch bản khả quan,
Kịch bản tiêu cực, Base case, Best case, Worst case...) để tránh trộn lẫn ngữ cảnh số liệu dự báo.
"""

from __future__ import annotations

import re

from rag_document_pipeline.models import LayoutElement

# Mẫu regex nhận diện tên kịch bản kinh doanh / dự báo tài chính
_SCENARIO_RE = re.compile(
    r"(?i)\b(kịch bản cơ sở|kịch bản khả quan|kịch bản tích cực|kịch bản tiêu cực|"
    r"kịch bản thận trọng|base case|best case|worst case|optimistic|pessimistic)\b"
)


class BusinessPlanPolicy:
    """Xác định ranh giới kịch bản kinh doanh để bảo toàn số liệu dự báo trong đúng ngữ cảnh."""

    @staticmethod
    def scenario(element: LayoutElement) -> str | None:
        """Trích xuất tên kịch bản nếu có trong văn bản của phần tử.

        Args:
            element: Phần tử LayoutElement.

        Returns:
            str | None: Tên kịch bản nếu khớp hoặc None.
        """
        match = _SCENARIO_RE.search(element.text)
        return match.group(1).strip() if match else None

    @classmethod
    def starts_scenario(cls, element: LayoutElement) -> bool:
        """Kiểm tra phần tử có phải là tiêu đề (heading) mở đầu cho một kịch bản mới hay không."""
        return element.type.lower() == "heading" and cls.scenario(element) is not None


__all__ = ["BusinessPlanPolicy"]
