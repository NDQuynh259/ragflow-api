"""Mô-đun bộ xử lý các phần tử chuyên biệt (Specialized Element Processors).

Cung cấp các bộ xử lý riêng cho Bảng biểu (TableProcessor), Hình ảnh (FigureProcessor),
và Biểu đồ (ChartProcessor) nhằm bảo toàn tối đa cấu trúc dữ liệu đa phương thức.
"""

from .chart import ChartProcessor
from .figure import FigureProcessor
from .table import TableProcessor

__all__ = ["ChartProcessor", "FigureProcessor", "TableProcessor"]
