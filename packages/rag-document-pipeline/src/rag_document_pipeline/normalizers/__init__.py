"""Mô-đun chuẩn hóa bố cục và ngữ cảnh tài liệu (Layout & Context Normalizers).

Cung cấp lớp `LayoutNormalizer` để tự động gắn kết caption/footnote vào bảng hoặc hình ảnh,
tránh phân mảnh thông tin ngữ cảnh khi băm nhỏ tài liệu.
"""

from __future__ import annotations

from .layout import LayoutNormalizer

__all__ = ["LayoutNormalizer"]
