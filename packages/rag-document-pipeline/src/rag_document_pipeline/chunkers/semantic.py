"""Semantic text chunker based on semantic sentence boundaries and topic shifts.

Splits text by identifying topic shifts between adjacent sentences or sentence
buffers using cosine distance of embeddings (or lexical overlap fallback),
constrained by min_chunk_size and max_chunk_size to maintain optimal retrieval windows.
"""

from __future__ import annotations

import math
import re
import uuid
from collections.abc import Callable
from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter

from rag_document_pipeline.chunkers.base import estimate_tokens, group_by_section
from rag_document_pipeline.models import DocumentChunk, LayoutElement


class SemanticTextChunker:
    """Chunks text elements based on semantic topic shifts between sentences.

    Within each heading section, sentences are analyzed for topic continuity.
    When semantic distance exceeds the threshold, a chunk boundary is formed.
    Min and max size bounds are enforced so chunks remain optimal for LLM retrieval.
    """

    def __init__(
        self,
        *,
        embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
        min_chunk_size: int = 300,
        max_chunk_size: int = 1500,
        threshold_percentile: float = 80.0,
    ) -> None:
        self.embed_fn = embed_fn
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size
        self.threshold_percentile = threshold_percentile
        self._fallback_splitter = RecursiveCharacterTextSplitter(
            chunk_size=max_chunk_size,
            chunk_overlap=150,
            separators=["\n\n", "\n", ". ", ", ", " ", ""],
            length_function=len,
        )

    def chunk(
        self,
        elements: list[LayoutElement],
        *,
        document_id: str,
    ) -> list[DocumentChunk]:
        """Group elements by section, segment semantically, and return chunks."""
        if not elements:
            return []

        groups = self._group_by_section(elements)
        chunks: list[DocumentChunk] = []

        for group in groups:
            heading_prefix = self._heading_prefix(group)
            body = "\n\n".join(
                self._element_text(el)
                for el in group
                if self._element_text(el) and el.type.lower() != "heading"
            )
            if not body:
                continue

            all_pages = [el.page_number for el in group]
            all_ids = [el.id for el in group]
            all_bboxes = [el.bbox for el in group if el.bbox]
            section_path = group[0].section_path if group else []

            has_table = any(el.type.lower() in ("table", "data_table") for el in group)
            has_footnote = any(bool(el.metadata.get("footnote")) for el in group)
            metadata: dict[str, Any] = {"chunker": "semantic_hybrid"}
            if has_table:
                metadata["contains_table"] = True
                metadata["table_ids"] = [
                    el.id for el in group if el.type.lower() in ("table", "data_table")
                ]
            if has_footnote:
                metadata["contains_footnote"] = True
                metadata["footnote"] = next(
                    (el.metadata["footnote"] for el in group if el.metadata.get("footnote")),
                    None,
                )

            # Phân đoạn nội dung văn bản theo ranh giới ngữ nghĩa (Topic Shift Boundaries)
            text_segments = self._split_semantically(body)

            for segment in text_segments:
                if not segment.strip():
                    continue
                full_content = (
                    f"{heading_prefix}\n\n{segment.strip()}"
                    if heading_prefix
                    else segment.strip()
                )

                chunks.append(
                    DocumentChunk(
                        id=str(uuid.uuid4()),
                        document_id=document_id,
                        content=full_content,
                        index=len(chunks),
                        page_start=min(all_pages),
                        page_end=max(all_pages),
                        element_ids=all_ids,
                        bboxes=all_bboxes,
                        kind="text",
                        section_path=section_path,
                        token_count=estimate_tokens(full_content),
                        metadata=metadata,
                    )
                )

        return chunks

    @classmethod
    def _element_text(cls, el: LayoutElement) -> str:
        """Trích xuất chuỗi văn bản của một element, render bảng sang Markdown nếu cần."""
        if el.type.lower() in ("table", "data_table") and el.table_data:
            from rag_document_pipeline.chunkers.table import TableChunker

            return TableChunker.render_markdown(el)
        return el.text.strip()

    # ------------------------------------------------------------------
    # 1. Tách câu tiếng Việt chuẩn hóa (Vietnamese Sentence Boundary Detection)
    # ------------------------------------------------------------------
    @classmethod
    def _split_sentences(cls, text: str) -> list[str]:
        """Tách văn bản thành danh sách câu logic, bảo vệ từ viết tắt tiếng Việt, số và bảng Markdown.

        Các vấn đề giải quyết:
        1. Bảo tồn khối bảng Markdown: Bảng biểu (các dòng bắt đầu bằng '|') không bị
           xé lẻ thành từng câu theo dòng mà được giữ nguyên khối nguyên tử (atomic block).
        2. Dùng ký tự đặc biệt (Private Use Area Unicode '\\uE000') để che (mask) dấu chấm bên trong:
           - Viết tắt chức danh, học vị: ThS., TS., GS., PGS., BS., DS., KTS., đ/c...
           - Viết tắt hành chính, địa danh: TP., đ/v., v.v., K/g., tr., NĐ-CP., QĐ., TT....
           - Viết tắt tiếng Anh phổ biến: e.g., i.e., etc., vs., St., Mr., Mrs....
           - Số thập phân và dấu phân cách hàng nghìn: 1.5, 1.500.000, 10.000...
        3. Tách câu theo ranh giới chuẩn [.?!;…\\n].
        4. Hoàn nguyên (unmask) ký tự '\\uE000' trở lại thành dấu chấm ban đầu.
        """
        if not text or not text.strip():
            return []

        # Bước 1: Nhận diện và cô lập các khối bảng Markdown
        lines = text.split("\n")
        blocks: list[str] = []
        table_lines: list[str] = []

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("|") and stripped.endswith("|"):
                table_lines.append(line)
            else:
                if table_lines:
                    blocks.append("\n".join(table_lines))
                    table_lines = []
                if stripped:
                    blocks.append(line)
        if table_lines:
            blocks.append("\n".join(table_lines))

        # Bước 2: Xử lý tách câu cho từng block văn bản
        sentences: list[str] = []
        for block in blocks:
            # Nếu block là một bảng Markdown, coi cả bảng là một khối ngữ nghĩa hoàn chỉnh (atomic block)
            if block.strip().startswith("|") and block.strip().endswith("|"):
                sentences.append(block.strip())
                continue

            # Che dấu chấm trong số thập phân và phân cách hàng nghìn (vd: 1.500.000 hoặc 1.5)
            # Regex: chữ số + '.' + chữ số
            masked_block = re.sub(r"(?<=\d)\.(?=\d)", "\uE000", block)

            # Che dấu chấm trong các từ viết tắt tiếng Việt & tiếng Anh thông dụng
            abbrev_patterns = [
                r"\bTP\.",
                r"\bThS\.",
                r"\bTS\.",
                r"\bGS\.",
                r"\bPGS\.",
                r"\bBS\.",
                r"\bDS\.",
                r"\bKTS\.",
                r"\bđ/c\.",
                r"\bđ/v\.",
                r"\bv\.v\.",
                r"\bv\.v",
                r"\bK/g\.",
                r"\btr\.",
                r"\bNĐ-CP\.",
                r"\bQĐ\.",
                r"\bTT\.",
                r"\be\.g\.",
                r"\bi\.e\.",
                r"\betc\.",
                r"\bvs\.",
                r"\bMr\.",
                r"\bMrs\.",
                r"\bMs\.",
                r"\bDr\.",
                r"\bProf\.",
            ]
            for pat in abbrev_patterns:
                masked_block = re.sub(
                    pat,
                    lambda m: m.group(0).replace(".", "\uE000"),
                    masked_block,
                    flags=re.IGNORECASE,
                )

            # Tách câu theo ranh giới câu hợp lệ: dấu chấm, hỏi, cảm, chấm phẩy, ba chấm, xuống dòng
            split_raw = [
                s.strip()
                for s in re.split(r"(?<=[.?!;…\n])\s+", masked_block)
                if s.strip()
            ]

            # Hoàn nguyên lại dấu chấm từ ký tự mask
            for s in split_raw:
                sentences.append(s.replace("\uE000", "."))

        return sentences

    # ------------------------------------------------------------------
    # 2. Cắt đoạn văn bản theo ranh giới ngữ nghĩa (Semantic Splitting)
    # ------------------------------------------------------------------
    def _split_semantically(self, text: str) -> list[str]:
        """Tách văn bản dài thành các đoạn nhỏ dựa trên ranh giới chuyển dịch chủ đề (Topic Shifts).

        Quy trình:
        1. Tách văn bản thành danh sách câu logic qua `_split_sentences`.
        2. Nếu số lượng câu <= 1 hoặc toàn bộ đoạn văn ngắn hơn `min_chunk_size`, giữ nguyên cả đoạn.
        3. Sử dụng Cửa sổ trượt (Sliding Window Buffer) để tính khoảng cách ngữ nghĩa giữa các cụm câu liền kề.
        4. Xác định ngưỡng ngắt (Breakpoints) theo phân vị `threshold_percentile` (mặc định 80%).
        5. Gom các câu nằm giữa các điểm ngắt thành các cụm ngữ nghĩa (Semantic Clusters).
        6. Áp dụng `_enforce_bounds`:
           - Cụm nào < min_chunk_size -> Lũy tiến gộp với cụm tiếp theo (Gộp phần nhỏ cùng ý).
           - Cụm nào > max_chunk_size -> Cắt tiếp đệ quy theo dấu câu (Cắt phần quá dài).
        """
        sentences = self._split_sentences(text)
        if len(sentences) <= 1 or len(text) <= self.min_chunk_size:
            return [text]

        # Tính khoảng cách ngữ nghĩa giữa các cửa sổ trượt (Sliding Window Buffer)
        distances = self._compute_distances(sentences, window_size=2)
        if not distances:
            return [text]

        # Tính toán ngưỡng ngắt chuyển đổi chủ đề (Topic Shift Breakpoint Threshold)
        threshold = self._calculate_threshold(distances)

        # Xác định các chỉ số câu cần cắt ranh giới
        split_indices: list[int] = []
        for idx, dist in enumerate(distances):
            if dist >= threshold:
                split_indices.append(idx + 1)

        # Gom câu thành các cụm ngữ nghĩa
        clusters: list[str] = []
        start_idx = 0
        for split_idx in split_indices:
            cluster_text = self._join_sentences(sentences[start_idx:split_idx])
            if cluster_text:
                clusters.append(cluster_text)
            start_idx = split_idx
        remaining = self._join_sentences(sentences[start_idx:])
        if remaining:
            clusters.append(remaining)

        # Ràng buộc kích thước min_chunk_size và max_chunk_size
        return self._enforce_bounds(clusters)

    @staticmethod
    def _join_sentences(sentences: list[str]) -> str:
        """Ghép các câu lại với nhau, giữ nguyên định dạng ngắt dòng cho Bảng Markdown."""
        result_parts: list[str] = []
        for s in sentences:
            if not s:
                continue
            if s.startswith("|") and s.endswith("|"):
                result_parts.append(f"\n\n{s}\n\n")
            else:
                result_parts.append(s)
        joined = " ".join(result_parts).strip()
        return re.sub(r"\n{3,}", "\n\n", joined)

    # ------------------------------------------------------------------
    # 3. Đo khoảng cách ngữ nghĩa bằng Sliding Window Buffer
    # ------------------------------------------------------------------
    def _compute_distances(
        self,
        sentences: list[str],
        window_size: int = 2,
    ) -> list[float]:
        """Tính khoảng cách ngữ nghĩa giữa các cụm câu liền kề bằng Cửa sổ trượt (Sliding Window Buffer).

        Thay vì chỉ so sánh 2 câu đơn lẻ S[i] và S[i+1] (vốn dễ gây nhiễu do các câu ngắn liên từ như
        'Cụ thể là:', 'Theo đó:'), thuật toán gom:
        - Buffer bên trái (Left Buffer): window_size câu kết thúc tại vị trí i.
        - Buffer bên phải (Right Buffer): window_size câu bắt đầu từ vị trí i+1.

        Sau đó tính độ lệch ngữ nghĩa:
        1. Vector Cosine Distance: Nếu có mô hình Embedding (embed_fn).
        2. Lexical Jaccard Overlap Distance: Thuật toán dự phòng (Zero-cost fallback chạy offline 100%).
        """
        n = len(sentences)
        if n < 2:
            return []

        # Xây dựng các cặp Buffer trượt (Left Buffer vs Right Buffer)
        left_buffers: list[str] = []
        right_buffers: list[str] = []
        for i in range(n - 1):
            left_start = max(0, i - window_size + 1)
            left_chunk = " ".join(sentences[left_start : i + 1])
            right_end = min(n, i + 1 + window_size)
            right_chunk = " ".join(sentences[i + 1 : right_end])
            left_buffers.append(left_chunk)
            right_buffers.append(right_chunk)

        # 1. Nếu có hàm embedding (embed_fn), dùng True Vector Cosine Distance
        if self.embed_fn:
            try:
                # Batch embedding toàn bộ buffer một lần duy nhất để tối ưu hiệu năng
                all_buffers = left_buffers + right_buffers
                embeddings = self.embed_fn(all_buffers)
                left_embs = embeddings[: len(left_buffers)]
                right_embs = embeddings[len(left_buffers) :]

                distances: list[float] = []
                for v1, v2 in zip(left_embs, right_embs, strict=False):
                    dot = sum(a * b for a, b in zip(v1, v2, strict=False))
                    norm1 = math.sqrt(sum(a * a for a in v1))
                    norm2 = math.sqrt(sum(b * b for b in v2))
                    sim = dot / (norm1 * norm2) if norm1 > 0 and norm2 > 0 else 0.0
                    distances.append(1.0 - max(-1.0, min(1.0, sim)))
                return distances
            except Exception:
                pass  # Tự động chuyển sang fallback từ vựng nếu API embedding gặp sự cố

        # 2. Thuật toán dự phòng: Lexical-Semantic Token Overlap (Zero-cost Jaccard)
        distances = []
        for l_buf, r_buf in zip(left_buffers, right_buffers, strict=False):
            s1 = set(re.findall(r"\w+", l_buf.lower()))
            s2 = set(re.findall(r"\w+", r_buf.lower()))
            if not s1 or not s2:
                distances.append(0.5)
                continue
            intersection = len(s1 & s2)
            union = len(s1 | s2)
            jaccard_sim = intersection / union if union > 0 else 0.0
            distances.append(1.0 - jaccard_sim)
        return distances

    def _calculate_threshold(self, distances: list[float]) -> float:
        """Xác định ngưỡng ngắt khoảng cách tại phân vị threshold_percentile (mặc định 80%)."""
        if not distances:
            return 0.5
        sorted_dist = sorted(distances)
        k = (len(sorted_dist) - 1) * (self.threshold_percentile / 100.0)
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return sorted_dist[int(k)]
        d0 = sorted_dist[int(f)] * (c - k)
        d1 = sorted_dist[int(c)] * (k - f)
        return d0 + d1

    # ------------------------------------------------------------------
    # 4. Ràng buộc kích thước: Gộp phần nhỏ & Cắt phần dài
    # ------------------------------------------------------------------
    def _enforce_bounds(self, clusters: list[str]) -> list[str]:
        """Ràng buộc kích thước: Gộp cụm nhỏ (< min_chunk_size) và Cắt cụm quá dài (> max_chunk_size).

        - Bài toán Gộp phần nhỏ: Nếu cụm câu chưa đạt `min_chunk_size`, nó sẽ được lũy tiến
          ghép với cụm câu tiếp theo nhằm tránh tạo ra các chunk quá ngắn gây loãng vector.
        - Bài toán Cắt phần dài: Nếu cụm câu dài vượt quá `max_chunk_size`, sử dụng
          `_fallback_splitter` đệ quy theo các mức dấu phân đoạn (paragraphs, sentences)
          để không làm tràn context window của LLM.
        """
        merged: list[str] = []
        current = ""

        for cluster in clusters:
            if not current:
                current = cluster
            elif len(current) + len(cluster) + 2 <= self.min_chunk_size:
                # Nối tiếp nếu chưa đạt ngưỡng tối thiểu
                separator = "\n\n" if ("|" in current or "|" in cluster or "\n" in current) else " "
                current = f"{current}{separator}{cluster}"
            else:
                merged.append(current)
                current = cluster
        if current:
            merged.append(current)

        # Tách các cụm vượt quá max_chunk_size
        final_segments: list[str] = []
        for seg in merged:
            if len(seg) > self.max_chunk_size:
                final_segments.extend(self._fallback_splitter.split_text(seg))
            else:
                final_segments.append(seg)

        return final_segments

    _group_by_section = staticmethod(group_by_section)

    @staticmethod
    def _heading_prefix(group: list[LayoutElement]) -> str:
        """Trích xuất tiêu đề phân cấp từ group để làm context prefix cho chunk (### H1 > H2)."""
        if group and group[0].section_path:
            return "### " + " > ".join(group[0].section_path)
        headings = [el.text.strip() for el in group if el.type == "heading" and el.text.strip()]
        if headings:
            return "### " + " > ".join(headings)
        return ""
