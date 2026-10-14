"""Base chunker protocol for document chunking strategies.

Mô-đun này định nghĩa giao diện chuẩn (Protocol) mà mọi bộ băm nhỏ tài liệu (Chunker)
trong hệ thống đều phải tuân thủ.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from rag_document_pipeline.models import DocumentChunk, LayoutElement


@runtime_checkable
class Chunker(Protocol):
    """Giao diện (Protocol) chuẩn cho tất cả các triển khai Chunker.

    Bất kỳ lớp nào cài đặt phương thức `chunk` với chữ ký tương thích đều được
    coi là một Chunker hợp lệ mà không cần kế thừa trực tiếp (Structural Subtyping).
    """

    def chunk(
        self,
        elements: list[LayoutElement],
        *,
        document_id: str,
    ) -> list[DocumentChunk]:
        """Chia nhỏ danh sách LayoutElement thành các DocumentChunk độc lập.

        Args:
            elements: Danh sách các phần tử bố cục (đoạn văn, tiêu đề, bảng, hình ảnh...).
            document_id: Định danh duy nhất của tài liệu gốc đang được xử lý.

        Returns:
            Danh sách các DocumentChunk hoàn chỉnh, sẵn sàng cho pha lưu trữ và nhúng vector.
        """
        ...


__all__ = [
    "Chunker",
]
