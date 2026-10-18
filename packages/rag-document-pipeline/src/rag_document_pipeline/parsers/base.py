"""Định nghĩa giao diện cơ sở (Base Interfaces) và ngoại lệ cho các bộ phân tích cú pháp tài liệu."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from rag_document_pipeline.models import LayoutElement


class ParserError(RuntimeError):
    """Ngoại lệ phát sinh khi bộ phân tích không thể trích xuất các phần tử bố cục từ tài liệu."""


class Parser(Protocol):
    """Giao thức chuẩn cho mọi bộ phân tích tài liệu (Document Parser) trong hệ thống."""

    def parse(
        self,
        content: bytes,
        *,
        filename: str,
        image_dir: str | Path | None = None,
    ) -> list[LayoutElement]:
        """Phân tích dữ liệu nhị phân của tài liệu thành danh sách phần tử bố cục LayoutElement.

        Args:
            content: Dữ liệu nhị phân (bytes) của tài liệu nguồn.
            filename: Tên tệp tin gốc (bao gồm phần mở rộng như .pdf, .docx).
            image_dir: Đường dẫn thư mục để lưu các hình ảnh được trích xuất (tùy chọn).

        Returns:
            list[LayoutElement]: Danh sách các phần tử bố cục được trích xuất.
        """
        ...
