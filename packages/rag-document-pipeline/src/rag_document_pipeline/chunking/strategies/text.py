"""Semantic text chunker: Vietnamese-safe sentence split + topic-shift detection.

Mô-đun này cài đặt chiến lược băm văn bản thông minh (Semantic Hybrid Text Chunking):
1. Chuẩn hóa & tách câu an toàn cho tiếng Việt:
   - Bảo vệ các từ viết tắt học hàm/học vị/chức danh (ThS, TS, GS, PGS, BS, v.v.).
   - Bảo vệ dấu chấm trong số thập phân (ví dụ: 3.14, 150.5).
   - Bảo toàn nguyên vẹn các khối bảng biểu Markdown inline (table blocks).
2. Phát hiện điểm nhảy vọt chủ đề (Topic Shift Detection):
   - Sử dụng cửa sổ trượt (Sliding Window Buffer) $k=2$ câu liền kề.
   - Đo khoảng cách ngữ nghĩa giữa hai cửa sổ liên tiếp (bằng Cosine Distance qua Embedding
     hoặc Lexical Jaccard Distance làm fallback).
   - Xác định ngưỡng cắt chunk dựa trên xếp hạng bách phân vị (Percentile Threshold).
3. Kiểm soát cận kích thước (Size Bounds Enforcement):
   - Gộp lũy tiến các mẩu câu quá ngắn nếu nhỏ hơn `min_chunk_size`.
   - Cắt đệ quy theo dấu ngắt tự nhiên nếu đoạn văn bản vượt quá `max_chunk_size`.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from typing import Any

from core.uuid7 import uuid7_str
from rag_document_pipeline.models import DocumentChunk, LayoutElement

from ..core import (
    cosine_distance,
    estimate_tokens,
    group_by_section,
    jaccard_distance,
    propagate_sections,
)
from ..core.constants import ABBREV_PATTERN, DECIMAL_PATTERN, MASK_CHAR


class TextChunker:
    """Chiến lược băm văn bản dựa trên phát hiện chuyển đổi chủ đề (Topic Shifts).

    Kết hợp giữa phân tích cấu trúc cây phân cấp chương mục và khoảng cách vector ngữ nghĩa
    để tạo ra các chunk văn bản trọn vẹn ý tứ, không bị ngắt cụt giữa câu hay giữa ý.
    """

    def __init__(
        self,
        *,
        min_chunk_size: int = 300,
        max_chunk_size: int = 1500,
        threshold_percentile: float = 80.0,
        window_size: int = 2,
        embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
    ) -> None:
        """Khởi tạo TextChunker với các tham số giới hạn và mô hình nhúng.

        Args:
            min_chunk_size: Kích thước tối thiểu của một chunk (ký tự). Các đoạn ngắn hơn sẽ được gộp lại.
            max_chunk_size: Kích thước tối đa của một chunk (ký tự). Các đoạn dài hơn sẽ bị chia nhỏ.
            threshold_percentile: Ngưỡng bách phân vị (0 < p <= 100). Khoảng cách ngữ nghĩa vượt ngưỡng này
                sẽ được xem là điểm bắt đầu của một chủ đề mới và kích hoạt cắt chunk.
            window_size: Bán kính cửa sổ câu (số lượng câu trước và sau điểm chia) dùng để đo ngữ cảnh.
            embed_fn: Hàm nhúng vector để tính khoảng cách Cosine giữa các cửa sổ câu; nếu None sẽ dùng Jaccard.
        """
        if min_chunk_size <= 0 or max_chunk_size < min_chunk_size:
            raise ValueError("Kích thước giới hạn min_chunk_size hoặc max_chunk_size không hợp lệ")
        if not 0 < threshold_percentile <= 100:
            raise ValueError("threshold_percentile phải nằm trong khoảng (0, 100]")
        if window_size < 1:
            raise ValueError("window_size phải là số nguyên dương >= 1")
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size
        self.threshold_percentile = threshold_percentile
        self.window_size = window_size
        self.embed_fn = embed_fn

    def chunk(
        self,
        elements: list[LayoutElement],
        *,
        document_id: str,
    ) -> list[DocumentChunk]:
        """Gom nhóm phần tử theo chương mục và băm nội dung tại ranh giới ngữ nghĩa.

        Args:
            elements: Danh sách LayoutElement cần băm.
            document_id: Mã định danh tài liệu gốc.

        Returns:
            Danh sách các DocumentChunk văn bản đã được gắn breadcrumb tiêu đề.
        """
        # Lan truyền cây tiêu đề để các phần tử kế thừa đầy đủ đường dẫn chương mục
        elements = propagate_sections(elements)
        chunks: list[DocumentChunk] = []

        for group in group_by_section(elements):
            body = self._group_text(group)
            if not body:
                continue

            # 1. Tách văn bản tại điểm nhảy vọt ngữ nghĩa, sau đó ép cận min/max kích thước
            segments = self._enforce_bounds(self._split_semantically(body))
            metadata: dict[str, Any] = {"chunker": "semantic_hybrid", "modality": "text"}

            # Lọc các phần tử văn bản để lấy thông tin metadata (bỏ qua heading, table, image)
            non_text_types = {
                "heading",
                "table",
                "data_table",
                "image",
                "figure",
                "header",
                "footer",
            }
            text_elements = [el for el in group if el.type.lower() not in non_text_types]
            if not text_elements:
                continue

            # Tính toán tọa độ và phạm vi trang của khối văn bản
            page_start = min(el.page_number for el in text_elements)
            page_end = max(el.page_number for el in text_elements)
            element_ids = [el.id for el in text_elements]
            bboxes = [el.bbox for el in text_elements if el.bbox]

            # Lấy breadcrumb chương mục từ heading cuối cùng hoặc section_path của group
            section_path = next((el.section_path for el in group if el.section_path), [])
            heading_elements = [el for el in group if el.type.lower() == "heading"]
            if heading_elements:
                section_path = list(heading_elements[-1].section_path)

            prefix_path = list(section_path)

            # 2. Đóng gói từng segment thành DocumentChunk kèm tiền tố breadcrumb
            for segment in segments:
                content = (
                    f"### {' > '.join(prefix_path)}\n\n{segment}".strip()
                    if prefix_path
                    else segment
                )
                chunks.append(
                    DocumentChunk(
                        id=uuid7_str(),
                        document_id=document_id,
                        content=content,
                        page_start=page_start,
                        page_end=page_end,
                        element_ids=element_ids,
                        bboxes=bboxes,
                        kind="text",
                        section_path=list(section_path),
                        token_count=estimate_tokens(content),
                        metadata=dict(metadata),
                    )
                )
        return chunks

    # --------------------------------------------------------------------------
    # 1. Gom nội dung văn bản (Text assembly)
    # --------------------------------------------------------------------------

    @staticmethod
    def _group_text(group: list[LayoutElement]) -> str:
        """Ghép nối nội dung của các phần tử văn bản trong nhóm, bỏ qua heading và modalities khác.

        Args:
            group: Nhóm phần tử liên tiếp trong cùng section và cùng trang.

        Returns:
            Chuỗi văn bản các phần tử nối nhau bằng dòng trống; heading, bảng và ảnh đã loại bỏ.
        """
        parts: list[str] = []
        for el in group:
            if el.type.lower() in (
                "heading",
                "table",
                "data_table",
                "image",
                "figure",
                "header",
                "footer",
            ):
                continue
            value = el.text.strip()
            if value:
                parts.append(value)
        return "\n\n".join(parts)

    # --------------------------------------------------------------------------
    # 2. Tách câu an toàn tiếng Việt (Sentence splitting)
    # --------------------------------------------------------------------------

    @classmethod
    def _split_sentences(cls, text: str) -> list[str]:
        """Tách chuỗi văn bản thành danh sách câu hoàn chỉnh có bảo vệ ngữ pháp tiếng Việt.

        Quy trình xử lý:
        1. Thu thập các khối văn bản, giữ nguyên khối bảng Markdown nếu có.
        2. Tạm che (mask) dấu chấm trong từ viết tắt (ThS., TS.) và số thập phân (1.5).
        3. Tách câu theo dấu ngắt câu (.?!;… hoặc xuống dòng).
        4. Hoàn trả lại dấu chấm gốc và làm sạch khoảng trắng thừa.

        Args:
            text: Chuỗi văn bản của một lô phần tử đã ghép nối.

        Returns:
            Danh sách câu đã gỡ mặt nạ và cắt khoảng trắng; danh sách rỗng nếu văn bản trống.
        """
        if not text or not text.strip():
            return []

        blocks = cls._collect_blocks(text)
        sentences: list[str] = []
        for block in blocks:
            # Nếu là khối bảng biểu inline, giữ nguyên khối không tách vụn câu
            if cls._is_table_block(block):
                sentences.append(block)
                continue

            # Thay thế dấu chấm trong từ viết tắt bằng ký tự mặt nạ tạm
            masked = ABBREV_PATTERN.sub(lambda match: match.group(0).replace(".", MASK_CHAR), block)
            # Thay thế dấu chấm trong số thập phân bằng ký tự mặt nạ tạm
            masked = DECIMAL_PATTERN.sub(rf"\1{MASK_CHAR}\2", masked)

            # Tách chuỗi theo dấu ngắt câu hoặc dấu xuống dòng
            parts = re.split(r"[.?!;…]+|\n+", masked)
            for part in parts:
                value = part.replace(MASK_CHAR, ".").strip()
                if value:
                    sentences.append(value)
        return sentences

    @staticmethod
    def _collect_blocks(text: str) -> list[str]:
        """Gom các dòng văn bản, phân biệt giữa văn bản thông thường và khối bảng Markdown.

        Args:
            text: Chuỗi văn bản nhiều dòng cần chia khối.

        Returns:
            Danh sách khối: mỗi dòng văn bản thường là một khối, các dòng `| ... |`
            liền kề được gộp thành một khối bảng duy nhất.
        """
        blocks: list[str] = []
        table_lines: list[str] = []
        for line in text.split("\n"):
            stripped = line.strip()
            if stripped.startswith("|") and stripped.endswith("|"):
                table_lines.append(line)
                continue
            if table_lines:
                blocks.append("\n".join(table_lines))
                table_lines = []
            if stripped:
                blocks.append(stripped)
        if table_lines:
            blocks.append("\n".join(table_lines))
        return blocks

    @staticmethod
    def _is_table_block(block: str) -> bool:
        """Kiểm tra xem khối văn bản có phải là bảng Markdown hay không.

        Args:
            block: Một khối văn bản từ `_collect_blocks`.

        Returns:
            True nếu mọi dòng của khối đều mở và đóng bằng ký tự `|`.
        """
        stripped = block.strip()
        return stripped.startswith("|") and stripped.endswith("|")

    # --------------------------------------------------------------------------
    # 3. Tính khoảng cách ngữ nghĩa & Ngưỡng cắt (Semantic distance)
    # --------------------------------------------------------------------------

    def _compute_distances(
        self, sentences: list[str], window_size: int | None = None
    ) -> list[float]:
        """Tính toán khoảng cách ngữ nghĩa giữa các cửa sổ trượt câu liền kề.

        Tại mỗi ranh giới giữa câu i và câu i+1:
        - Gom cửa sổ bên trái gồm window_size câu trước đó: [i - window + 1 ... i].
        - Gom cửa sổ bên phải gồm window_size câu kế tiếp: [i + 1 ... i + 1 + window].
        - Tính khoảng cách Cosine qua `embed_fn`, hoặc fallback sang khoảng cách Jaccard.

        Args:
            sentences: Danh sách câu đã tách của một lô văn bản.
            window_size: Số câu mỗi bên cửa sổ trượt; None dùng `self.window_size`.

        Returns:
            Danh sách khoảng cách tại từng ranh giới câu, dài hơn danh sách câu một đơn vị.
        """
        window = window_size or self.window_size
        if len(sentences) < 2:
            return []

        buffers: list[tuple[str, str]] = []
        for i in range(len(sentences) - 1):
            left = " ".join(sentences[max(0, i + 1 - window) : i + 1])
            right = " ".join(sentences[i + 1 : i + 1 + window])
            buffers.append((left, right))

        # Ưu tiên tính Cosine Distance qua mô hình Embedding
        if self.embed_fn:
            try:
                texts = [left for left, _ in buffers] + [right for _, right in buffers]
                vectors = self.embed_fn(texts)
                if len(vectors) != len(texts):
                    raise ValueError("embed_fn trả về số lượng vector không khớp")
                midpoint = len(buffers)
                return [
                    cosine_distance(vectors[index], vectors[index + midpoint])
                    for index in range(midpoint)
                ]
            except Exception:
                pass

        # Fallback: Tính khoảng cách từ vựng Jaccard
        return [jaccard_distance(left, right) for left, right in buffers]

    def _calculate_threshold(self, distances: list[float]) -> float:
        """Xác định ngưỡng khoảng cách theo phân vị bách phân (Percentile Ranking).

        Khoảng cách ngữ nghĩa vượt qua ngưỡng này được coi là điểm đổi ý (Topic Shift).

        Args:
            distances: Danh sách khoảng cách giữa các cặp cửa sổ câu liền kề.

        Returns:
            Giá trị ngưỡng tại bách phân vị `threshold_percentile`, có nội suy tuyến tính
            khi hạng không rơi đúng vào vị trí số nguyên; 1.0 nếu danh sách rỗng.
        """
        if not distances:
            return 1.0
        ordered = sorted(distances)
        rank = (len(ordered) - 1) * self.threshold_percentile / 100.0
        lower = math.floor(rank)
        upper = math.ceil(rank)
        if lower == upper:
            return ordered[lower]
        # Nội suy tuyến tính giữa lower và upper
        return ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)

    def _split_semantically(self, text: str) -> list[str]:
        """Chia văn bản thành các đoạn nhỏ tại vị trí có khoảng cách ngữ nghĩa >= ngưỡng bách phân vị.

        Args:
            text: Chuỗi văn bản của một lô phần tử đã ghép nối.

        Returns:
            Danh sách đoạn văn bản theo chủ đề; mỗi câu xuất hiện đúng một lần theo thứ tự gốc.
        """
        sentences = self._split_sentences(text)
        if len(sentences) <= 1:
            return [text]

        distances = self._compute_distances(sentences)
        threshold = self._calculate_threshold(distances)
        segments: list[list[str]] = [[]]

        for index, sentence in enumerate(sentences):
            segments[-1].append(sentence)
            # Nếu tại vị trí này khoảng cách vượt ngưỡng: kết thúc đoạn hiện tại và mở đoạn mới
            if index < len(distances) and distances[index] >= threshold:
                segments.append([])

        return [" ".join(segment) for segment in segments if segment]

    # --------------------------------------------------------------------------
    # 4. Kiểm soát cận kích thước (Size bounds enforcement)
    # --------------------------------------------------------------------------

    def _enforce_bounds(self, segments: list[str]) -> list[str]:
        """Đảm bảo các đoạn văn bản tuân thủ chặt chẽ ngưỡng `min_chunk_size` và `max_chunk_size`.

        - Bước 1: Gộp lũy tiến đoạn trước đó nếu độ dài của nó < min_chunk_size.
        - Bước 2: Chia đệ quy nếu đoạn văn bản vượt quá max_chunk_size.

        Args:
            segments: Danh sách đoạn thô sau bước tách theo topic shift.

        Returns:
            Danh sách đoạn đã nằm trong khoảng [min_chunk_size, max_chunk_size] ký tự.
        """
        merged: list[str] = []
        for segment in segments:
            if merged and len(merged[-1]) < self.min_chunk_size:
                merged[-1] = self._merge_segments(merged[-1], segment)
            else:
                merged.append(segment)

        result: list[str] = []
        for segment in merged:
            if len(segment) <= self.max_chunk_size:
                result.append(segment)
            else:
                result.extend(self._recursive_split(segment))
        return result

    @staticmethod
    def _merge_segments(left: str, right: str) -> str:
        """Gộp hai đoạn văn bản kề nhau, tôn trọng định dạng bảng Markdown nếu có.

        Args:
            left: Đoạn đứng trước.
            right: Đoạn đứng sau.

        Returns:
            Chuỗi đã gộp: cách bằng dòng trống nếu một trong hai đoạn là bảng Markdown,
            ngược lại nối bằng một khoảng trắng.
        """
        if left.startswith("|") or right.startswith("|"):
            return left + "\n\n" + right
        return left + " " + right

    def _recursive_split(self, text: str) -> list[str]:
        """Chia nhỏ đệ quy một đoạn văn bản quá dài theo thứ tự ưu tiên dấu ngắt tự nhiên.

        Thứ tự ưu tiên ngắt:
        1. '\\n\\n' (đoạn văn)
        2. '\\n' (dòng)
        3. '. ' (câu)
        4. ', ' (mệnh đề)
        5. Cắt cứng theo độ dài ký tự nếu không tìm thấy dấu ngắt phù hợp.

        Args:
            text: Đoạn văn bản vượt quá `max_chunk_size`.

        Returns:
            Danh sách các đoạn con, mỗi đoạn dài tối đa `max_chunk_size` ký tự.
        """
        for separator in ["\n\n", "\n", ". ", ", "]:
            pieces = text.split(separator)
            if len(pieces) <= 1:
                continue
            result: list[str] = []
            current = ""
            for piece in pieces:
                candidate = (current + separator + piece).strip() if current else piece
                if len(candidate) <= self.max_chunk_size:
                    current = candidate
                    continue
                if current:
                    result.append(current)
                if len(piece) > self.max_chunk_size:
                    for offset in range(0, len(piece), self.max_chunk_size):
                        result.append(piece[offset : offset + self.max_chunk_size])
                    current = ""
                else:
                    current = piece
            if current:
                result.append(current)
            return result

        # Fallback cuối cùng: cắt cứng theo max_chunk_size
        return [
            text[offset : offset + self.max_chunk_size]
            for offset in range(0, len(text), self.max_chunk_size)
        ]


__all__ = ["TextChunker"]
