"""Bộ chuẩn hóa bố cục — gắn kết các phần tử ngữ cảnh liền kề (Layout Normalizer).

Xử lý:
- Gắn kết các phần tử 'caption' (chú thích) đứng riêng lẻ vào bảng biểu ('table') hoặc hình ảnh ('image/figure') liền kề.
- Gắn kết các phần tử 'footnote' (chú thích chân bảng/ảnh) đứng riêng lẻ vào bảng hoặc ảnh đứng trước.
- Loại bỏ các phần tử mồ côi đã được hấp thụ để chúng không làm nhiễu các chunk văn bản thông thường.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from rag_document_pipeline.models import LayoutElement

# Các mẫu regex nhận diện heuristic cho tiêu đề chú thích (caption) và chú thích chân (footnote)
CAPTION_RE = re.compile(
    r"^(Bảng|Table|Hình|Figure|Sơ đồ|Biểu đồ|Chart|Diagram)\s*[\d\.\:\-]+",
    re.IGNORECASE,
)
FOOTNOTE_RE = re.compile(
    r"^(\(\*+\)|\*+|Ghi chú|Note\s*\:|Chú thích)",
    re.IGNORECASE,
)


class LayoutNormalizer:
    """Chuẩn hóa các phần tử bố cục bằng cách ghép nối các phần tử ngữ cảnh liền kề."""

    @classmethod
    def bind_captions_and_footnotes(
        cls,
        elements: Sequence[LayoutElement],
    ) -> list[LayoutElement]:
        """Gắn kết các phần tử caption/footnote đứng độc lập vào bảng biểu hoặc hình ảnh liền kề.

        Duyệt qua danh sách phần tử và kiểm tra các phần tử liền trước/liền sau:
        - Bảng biểu (Table): caption thường nằm ở phía trên (preceding), footnote nằm ở phía dưới (succeeding).
        - Hình ảnh (Figure): caption thường nằm ở phía dưới (succeeding), footnote nằm ngay sau caption.

        Args:
            elements: Chuỗi các LayoutElement ban đầu từ parser.

        Returns:
            list[LayoutElement]: Danh sách LayoutElement mới với caption/footnote đã được gắn vào phần tử
            mục tiêu và các phần tử mồ côi đã bị hấp thụ được loại bỏ.
        """
        if not elements:
            return []

        elements_list = list(elements)
        absorbed_indices: set[int] = set()

        for i, el in enumerate(elements_list):
            el_type = el.type.lower()

            if el_type in ("table", "data_table"):
                cls._bind_to_table(elements_list, i, absorbed_indices)
            elif el_type in ("image", "figure"):
                cls._bind_to_figure(elements_list, i, absorbed_indices)

        # Tạo danh sách kết quả cuối cùng loại bỏ các phần tử đã bị hấp thụ
        result: list[LayoutElement] = [
            el for idx, el in enumerate(elements_list) if idx not in absorbed_indices
        ]
        return result

    @classmethod
    def _bind_to_table(
        cls,
        elements: list[LayoutElement],
        idx: int,
        absorbed: set[int],
    ) -> None:
        table_el = elements[idx]
        current_caption = table_el.caption or (
            table_el.table_data.caption if table_el.table_data else None
        )

        # 1. Check PRECEDING element for caption (Table captions are often on top)
        if idx > 0 and (idx - 1) not in absorbed:
            prev_el = elements[idx - 1]
            if prev_el.page_number == table_el.page_number and cls._is_caption(prev_el, prefer_type="table"):
                caption_text = prev_el.text.strip()
                if not current_caption:
                    table_el.caption = caption_text
                    if table_el.table_data:
                        table_el.table_data.caption = caption_text
                    current_caption = caption_text
                absorbed.add(idx - 1)

        # 2. Check SUCCEEDING element for caption (or footnote)
        if idx + 1 < len(elements) and (idx + 1) not in absorbed:
            next_el = elements[idx + 1]
            if next_el.page_number == table_el.page_number:
                if not current_caption and cls._is_caption(next_el, prefer_type="table"):
                    caption_text = next_el.text.strip()
                    table_el.caption = caption_text
                    if table_el.table_data:
                        table_el.table_data.caption = caption_text
                    current_caption = caption_text
                    absorbed.add(idx + 1)
                elif cls._is_footnote(next_el):
                    table_el.metadata["footnote"] = next_el.text.strip()
                    absorbed.add(idx + 1)

        # 3. Check for footnote right after succeeding caption (i+2)
        if (
            idx + 2 < len(elements)
            and (idx + 1) in absorbed
            and (idx + 2) not in absorbed
        ):
            after_next = elements[idx + 2]
            if after_next.page_number == table_el.page_number and cls._is_footnote(after_next):
                table_el.metadata["footnote"] = after_next.text.strip()
                absorbed.add(idx + 2)

    @classmethod
    def _bind_to_figure(
        cls,
        elements: list[LayoutElement],
        idx: int,
        absorbed: set[int],
    ) -> None:
        fig_el = elements[idx]
        current_caption = fig_el.caption or (
            fig_el.image_data.caption if fig_el.image_data else None
        )

        # 1. Check SUCCEEDING element for caption (Figure captions are usually below)
        if idx + 1 < len(elements) and (idx + 1) not in absorbed:
            next_el = elements[idx + 1]
            if next_el.page_number == fig_el.page_number:
                if not current_caption and cls._is_caption(next_el, prefer_type="figure"):
                    caption_text = next_el.text.strip()
                    fig_el.caption = caption_text
                    if fig_el.image_data:
                        fig_el.image_data.caption = caption_text
                    current_caption = caption_text
                    absorbed.add(idx + 1)
                elif cls._is_footnote(next_el):
                    fig_el.metadata["footnote"] = next_el.text.strip()
                    absorbed.add(idx + 1)

        # 2. Check PRECEDING element if caption not found below
        if not current_caption and idx > 0 and (idx - 1) not in absorbed:
            prev_el = elements[idx - 1]
            if prev_el.page_number == fig_el.page_number and cls._is_caption(prev_el, prefer_type="figure"):
                caption_text = prev_el.text.strip()
                fig_el.caption = caption_text
                if fig_el.image_data:
                    fig_el.image_data.caption = caption_text
                current_caption = caption_text
                absorbed.add(idx - 1)

        # 3. Check for footnote after succeeding caption (i+2)
        if (
            idx + 2 < len(elements)
            and (idx + 1) in absorbed
            and (idx + 2) not in absorbed
        ):
            after_next = elements[idx + 2]
            if after_next.page_number == fig_el.page_number and cls._is_footnote(after_next):
                fig_el.metadata["footnote"] = after_next.text.strip()
                absorbed.add(idx + 2)

    @staticmethod
    def _is_caption(el: LayoutElement, prefer_type: str = "") -> bool:
        el_type = el.type.lower()
        if el_type == "caption":
            return True
        text = el.text.strip()
        if not text or len(text) > 300:
            return False
        if el_type in ("text", "paragraph", "heading"):
            if CAPTION_RE.match(text):
                return True
        return False

    @staticmethod
    def _is_footnote(el: LayoutElement) -> bool:
        el_type = el.type.lower()
        if el_type == "footnote":
            return True
        text = el.text.strip()
        if not text or len(text) > 400:
            return False
        if el_type in ("text", "paragraph"):
            if FOOTNOTE_RE.match(text):
                return True
        return False
