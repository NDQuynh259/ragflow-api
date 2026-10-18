"""Hàm tiện ích tạo chuỗi đường dẫn phân cấp mục lục (Section Breadcrumbs)."""

from rag_contracts import DocumentChunk


def section_breadcrumb(chunk: DocumentChunk) -> str:
    """Trả về đường dẫn phân cấp phân đoạn của chunk dưới dạng chuỗi breadcrumb ngắn gọn.

    Ví dụ: ['Chương I', 'Điều 1', 'Khoản 2'] -> 'Chương I > Điều 1 > Khoản 2'.

    Args:
        chunk: Đối tượng DocumentChunk chứa thuộc tính section_path.

    Returns:
        str: Chuỗi breadcrumb phân cách bằng ký tự ' > '.
    """
    return " > ".join(part.strip() for part in chunk.section_path if part.strip())


__all__ = ["section_breadcrumb"]
