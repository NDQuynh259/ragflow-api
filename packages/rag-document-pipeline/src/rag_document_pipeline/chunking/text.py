"""Semantic text chunker: Vietnamese-safe sentence split + topic-shift detection."""

from __future__ import annotations

import math
import re
import uuid
from collections.abc import Callable
from typing import Any

from rag_document_pipeline.chunking.base import estimate_tokens, group_by_section
from rag_document_pipeline.models import DocumentChunk, LayoutElement

MASK_CHAR = ""
ABBREV_PATTERN = re.compile(
    r"\b(ThS|TS|GS|PGS|BS|DS|KTS|TP|đ/c|đ/v|v\.v|NĐ-CP|QĐ|TT|e\.g|i\.e|etc|Mr|Mrs|Dr|Ms|Prof)\."
)
DECIMAL_PATTERN = re.compile(r"(\d)\.(\d)")


class TextChunker:
    """Splits text at topic-shift boundaries using an optional embedding or lexical fallback."""

    def __init__(
        self,
        *,
        min_chunk_size: int = 300,
        max_chunk_size: int = 1500,
        threshold_percentile: float = 80.0,
        window_size: int = 2,
        embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
    ) -> None:
        if min_chunk_size <= 0 or max_chunk_size < min_chunk_size:
            raise ValueError("Invalid chunk size bounds")
        if not 0 < threshold_percentile <= 100:
            raise ValueError("threshold_percentile must be in (0, 100]")
        if window_size < 1:
            raise ValueError("window_size must be positive")
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
        """Group elements by section and split their body at semantic boundaries."""
        chunks: list[DocumentChunk] = []
        for group in group_by_section(elements):
            prefix = self._heading_prefix(group)
            body = self._group_text(group)
            if not body:
                continue

            segments = self._enforce_bounds(self._split_semantically(body))
            has_table = any(el.type.lower() in ("table", "data_table") for el in group)
            metadata: dict[str, Any] = {"chunker": "semantic_hybrid", "modality": "text"}
            if has_table:
                metadata["contains_table"] = True
                metadata["table_ids"] = [
                    el.id for el in group if el.type.lower() in ("table", "data_table")
                ]

            page_start = min(el.page_number for el in group)
            page_end = max(el.page_number for el in group)
            element_ids = [el.id for el in group if el.type.lower() != "heading"]
            bboxes = [el.bbox for el in group if el.bbox and el.type.lower() != "heading"]
            section_path = next((el.section_path for el in group if el.section_path), [])

            for segment in segments:
                content = f"{prefix}\n\n{segment}".strip() if prefix else segment
                chunks.append(
                    DocumentChunk(
                        id=str(uuid.uuid4()),
                        document_id=document_id,
                        content=content,
                        page_start=page_start,
                        page_end=page_end,
                        element_ids=element_ids,
                        bboxes=bboxes,
                        kind="text",
                        section_path=list(section_path),
                        token_count=estimate_tokens(content),
                        metadata=metadata,
                    )
                )
        return chunks

    # ------------------------------------------------------------------
    # Text assembly
    # ------------------------------------------------------------------

    @staticmethod
    def _heading_prefix(group: list[LayoutElement]) -> str:
        path = next((el.section_path for el in group if el.section_path), None)
        return "### " + " > ".join(path) if path else ""

    @staticmethod
    def _group_text(group: list[LayoutElement]) -> str:
        parts: list[str] = []
        for el in group:
            if el.type.lower() == "heading":
                continue
            if el.type.lower() in ("table", "data_table") and el.table_data:
                from rag_document_pipeline.chunking.table import TableChunker

                value = TableChunker.render_markdown(el)
            else:
                value = el.text.strip()
            if value:
                parts.append(value)
        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # Sentence splitting
    # ------------------------------------------------------------------

    @classmethod
    def _split_sentences(cls, text: str) -> list[str]:
        """Split prose into sentences, protecting decimals, abbreviations, and Markdown tables."""
        if not text or not text.strip():
            return []

        blocks = cls._collect_blocks(text)
        sentences: list[str] = []
        for block in blocks:
            if cls._is_table_block(block):
                sentences.append(block)
                continue

            masked = ABBREV_PATTERN.sub(
                lambda match: match.group(0).replace(".", MASK_CHAR), block
            )
            masked = DECIMAL_PATTERN.sub(rf"\1{MASK_CHAR}\2", masked)
            parts = re.split(r"[.?!;…]+|\n+", masked)
            for part in parts:
                value = part.replace(MASK_CHAR, ".").strip()
                if value:
                    sentences.append(value)
        return sentences

    @staticmethod
    def _collect_blocks(text: str) -> list[str]:
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
        stripped = block.strip()
        return stripped.startswith("|") and stripped.endswith("|")

    # ------------------------------------------------------------------
    # Semantic distance
    # ------------------------------------------------------------------

    def _compute_distances(self, sentences: list[str], window_size: int | None = None) -> list[float]:
        window = window_size or self.window_size
        if len(sentences) < 2:
            return []

        buffers: list[tuple[str, str]] = []
        for i in range(len(sentences) - 1):
            left = " ".join(sentences[max(0, i + 1 - window) : i + 1])
            right = " ".join(sentences[i + 1 : i + 1 + window])
            buffers.append((left, right))

        if self.embed_fn:
            try:
                texts = [left for left, _ in buffers] + [right for _, right in buffers]
                vectors = self.embed_fn(texts)
                if len(vectors) != len(texts):
                    raise ValueError("embed_fn returned an unexpected number of vectors")
                midpoint = len(buffers)
                return [
                    self._cosine_distance(vectors[index], vectors[index + midpoint])
                    for index in range(midpoint)
                ]
            except Exception:
                pass

        return [self._jaccard_distance(left, right) for left, right in buffers]

    @staticmethod
    def _cosine_distance(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if not norm_a or not norm_b:
            return 1.0
        return 1.0 - max(-1.0, min(1.0, dot / (norm_a * norm_b)))

    @staticmethod
    def _jaccard_distance(left: str, right: str) -> float:
        left_words = set(re.findall(r"\w+", left.lower()))
        right_words = set(re.findall(r"\w+", right.lower()))
        if not left_words and not right_words:
            return 0.0
        union = left_words | right_words
        if not union:
            return 0.0
        return 1.0 - len(left_words & right_words) / len(union)

    def _calculate_threshold(self, distances: list[float]) -> float:
        if not distances:
            return 1.0
        ordered = sorted(distances)
        rank = (len(ordered) - 1) * self.threshold_percentile / 100.0
        lower = math.floor(rank)
        upper = math.ceil(rank)
        if lower == upper:
            return ordered[lower]
        return ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)

    def _split_semantically(self, text: str) -> list[str]:
        sentences = self._split_sentences(text)
        if len(sentences) <= 1:
            return [text]

        distances = self._compute_distances(sentences)
        threshold = self._calculate_threshold(distances)
        segments: list[list[str]] = [[]]
        for index, sentence in enumerate(sentences):
            segments[-1].append(sentence)
            if index < len(distances) and distances[index] >= threshold:
                segments.append([])
        return [" ".join(segment) for segment in segments if segment]

    # ------------------------------------------------------------------
    # Size bounds
    # ------------------------------------------------------------------

    def _enforce_bounds(self, segments: list[str]) -> list[str]:
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
        if left.startswith("|") or right.startswith("|"):
            return left + "\n\n" + right
        return left + " " + right

    def _recursive_split(self, text: str) -> list[str]:
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
        return [text[offset : offset + self.max_chunk_size] for offset in range(0, len(text), self.max_chunk_size)]


__all__ = ["TextChunker"]
