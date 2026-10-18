"""Chính sách phân đoạn tài liệu nội bộ và wiki (Wiki / Handbook Policy).

Ưu tiên phân đoạn theo cấu trúc tiêu đề (Heading-first), đảm bảo các bài viết wiki,
sổ tay nhân viên hoặc tài liệu hướng dẫn nội bộ được ngắt mạch rõ ràng theo từng chủ đề.
"""

from rag_document_pipeline.models import LayoutElement


class WikiPolicy:
    """Xác định ranh giới phân đoạn đáng tin cậy dựa trên tiêu đề Heading trước khi áp dụng semantic split."""

    @staticmethod
    def is_section_boundary(element: LayoutElement) -> bool:
        """Kiểm tra một phần tử có phải là ranh giới bắt đầu một phân đoạn mục lục mới hay không.

        Args:
            element: Phần tử LayoutElement.

        Returns:
            bool: True nếu là tiêu đề heading có nội dung chữ, ngược lại False.
        """
        return element.type.lower() == "heading" and bool(element.text.strip())


__all__ = ["WikiPolicy"]
