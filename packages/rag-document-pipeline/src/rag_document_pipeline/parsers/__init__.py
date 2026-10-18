"""Mô-đun phân tích cú pháp tài liệu (Document Parsers).

Cung cấp giao thức phân tích tài liệu `Parser`, lớp ngoại lệ `ParserError`,
bộ phân tích PDF cục bộ `OpenDataLoaderParser`, và hàm chuyển đổi payload `elements_from_payload`.
"""

from .base import Parser, ParserError
from .mapping import elements_from_payload
from .opendataloader import OpenDataLoaderParser

__all__ = ["Parser", "ParserError", "OpenDataLoaderParser", "elements_from_payload"]
