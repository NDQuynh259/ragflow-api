"""Gói chuyển đổi và chuẩn hóa dữ liệu phân tích cú pháp (Parser Adapters & IR Conversion).

Cung cấp các hàm tạo DocumentIR từ phần tử bố cục (adapter), bộ chuẩn hóa bố cục (LayoutNormalizer)
và giao thức phân tích cú pháp (Parser).
"""

from .adapter import document_ir_from_elements, element_ir_from_layout
from .base import Parser, ParserError
from .normalize import LayoutNormalizer

__all__ = [
    "LayoutNormalizer",
    "Parser",
    "ParserError",
    "document_ir_from_elements",
    "element_ir_from_layout",
]
