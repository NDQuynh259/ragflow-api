"""Hàm tiện ích thiết lập mối quan hệ liên kết giữa các chunk (Chunk Relationships)."""

from rag_contracts import DocumentChunk


def add_bidirectional_relationship(left: DocumentChunk, right: DocumentChunk) -> None:
    """Thiết lập liên kết hai chiều giữa hai chunk mà không làm trùng lặp mã ID.

    Thường dùng để kết nối giữa chunk văn bản dẫn xuất và chunk Bảng biểu/Hình ảnh
    (ví dụ: văn bản nhắc đến 'Xem Bảng 1' sẽ được liên kết trực tiếp với chunk chứa Bảng 1).

    Args:
        left: Chunk thứ nhất.
        right: Chunk thứ hai.
    """
    left_ids = left.metadata.setdefault("related_chunk_ids", [])
    right_ids = right.metadata.setdefault("related_chunk_ids", [])
    if right.id not in left_ids:
        left_ids.append(right.id)
    if left.id not in right_ids:
        right_ids.append(left.id)


__all__ = ["add_bidirectional_relationship"]
