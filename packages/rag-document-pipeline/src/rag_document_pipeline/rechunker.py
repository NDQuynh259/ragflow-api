"""Re-chunk a persisted ``layout.json`` without parsing the source document.

The module deliberately depends on the storage port only by duck typing: any
object exposing ``get(uri) -> bytes`` (including ``core.storage.ObjectStoragePort``)
can be used.  Layout files are JSON objects containing either ``elements`` or a
bare list of layout elements.
"""
from __future__ import annotations

import json
import math
import re
import uuid
from collections.abc import Callable
from typing import Any

from rag_document_pipeline.chunkers.base import estimate_tokens
from rag_document_pipeline.chunkers.figure import ImageChunker
from rag_document_pipeline.models import DocumentChunk, LayoutElement


class SemanticTextChunker:
    """Semantic text chunker with Vietnamese-safe sentence splitting.

    ``embed_fn`` is optional.  When omitted, lexical Jaccard distance is used,
    making re-chunking deterministic and offline.  ``embed_fn`` receives a
    list of strings and returns vectors (or a single vector for a scalar API).
    """

    _MASK = ""
    _ABBREVIATIONS = (
        "ThS", "TS", "GS", "PGS", "BS", "DS", "KTS", "TP", "đ/c", "đ/v",
        "v.v", "NĐ-CP", "QĐ", "TT", "e.g", "i.e", "etc", "Mr", "Mrs", "Dr",
    )

    def __init__(
        self,
        *,
        chunk_size: int = 1200,
        chunk_overlap: int = 200,
        min_chunk_size: int = 300,
        max_chunk_size: int = 1500,
        window_size: int = 2,
        threshold_percentile: float = 80.0,
        embed_fn: Callable[[Any], Any] | None = None,
    ) -> None:
        if chunk_size <= 0 or chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise ValueError("Invalid chunk window")
        if min_chunk_size < 0 or max_chunk_size < min_chunk_size:
            raise ValueError("Invalid semantic bounds")
        if window_size < 1 or not 0 < threshold_percentile <= 100:
            raise ValueError("Invalid semantic configuration")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size
        self.window_size = window_size
        self.threshold_percentile = threshold_percentile
        self.embed_fn = embed_fn

    @classmethod
    def _split_sentences(cls, text: str) -> list[str]:
        """Split prose while protecting decimal points and abbreviations."""
        if not text.strip():
            return []
        # Markdown tables are atomic blocks; splitting their rows loses schema.
        lines = text.splitlines()
        blocks: list[str] = []
        prose: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("|") and stripped.endswith("|"):
                if prose:
                    blocks.extend(cls._split_prose("\n".join(prose)))
                    prose = []
                blocks.append(stripped)
            else:
                prose.append(line)
        if prose:
            blocks.extend(cls._split_prose("\n".join(prose)))
        return [b.strip() for b in blocks if b.strip()]

    @classmethod
    def _split_prose(cls, text: str) -> list[str]:
        value = text
        # Mask decimal/thousands separators and dots in known abbreviations.
        value = re.sub(r"(?<=\d)\.(?=\d)", cls._MASK, value)
        for abbreviation in cls._ABBREVIATIONS:
            value = re.sub(
                rf"(?i)(?<!\w){re.escape(abbreviation)}\.",
                lambda m: m.group(0)[:-1] + cls._MASK,
                value,
            )
        parts = re.split(r"(?<=[.!?;…])\s+|\n+", value)
        return [p.replace(cls._MASK, ".").strip() for p in parts if p.strip()]

    @staticmethod
    def _tokens(value: str) -> set[str]:
        return set(re.findall(r"\w+", value.lower(), flags=re.UNICODE))

    @classmethod
    def _jaccard_distance(cls, left: str, right: str) -> float:
        a, b = cls._tokens(left), cls._tokens(right)
        if not a and not b:
            return 1.0
        return 1.0 - len(a & b) / len(a | b)

    def _distances(self, sentences: list[str]) -> list[float]:
        if len(sentences) < 2:
            return []
        pairs = [
            (
                " ".join(sentences[max(0, i - self.window_size + 1) : i + 1]),
                " ".join(sentences[i + 1 : i + 1 + self.window_size]),
            )
            for i in range(len(sentences) - 1)
        ]
        if self.embed_fn is None:
            return [self._jaccard_distance(a, b) for a, b in pairs]
        values = [a for pair in pairs for a in pair]
        vectors = self.embed_fn(values)
        if len(vectors) != len(values):
            raise ValueError("embed_fn must return one vector per input")
        out: list[float] = []
        for i in range(0, len(vectors), 2):
            x, y = vectors[i], vectors[i + 1]
            nx = math.sqrt(sum(v * v for v in x))
            ny = math.sqrt(sum(v * v for v in y))
            if not nx or not ny:
                out.append(1.0)
            else:
                out.append(1.0 - sum(a * b for a, b in zip(x, y)) / (nx * ny))
        return out

    def _calculate_threshold(self, distances: list[float]) -> float:
        if not distances:
            return 1.0
        ordered = sorted(distances)
        rank = (self.threshold_percentile / 100) * (len(ordered) - 1)
        lo, hi = math.floor(rank), math.ceil(rank)
        return ordered[lo] + (ordered[hi] - ordered[lo]) * (rank - lo)

    def _enforce_bounds(self, pieces: list[str]) -> list[str]:
        merged: list[str] = []
        for piece in pieces:
            if merged and len(merged[-1]) < self.min_chunk_size:
                merged[-1] += "\n\n" + piece
            else:
                merged.append(piece)
        result: list[str] = []
        for piece in merged:
            if len(piece) <= self.max_chunk_size:
                result.append(piece)
                continue
            # Preserve sentence boundaries where possible, then hard split.
            words = piece.split()
            current = ""
            for word in words:
                if current and len(current) + len(word) + 1 > self.max_chunk_size:
                    result.append(current)
                    current = word
                else:
                    current = (current + " " + word).strip()
            if current:
                result.append(current)
        return result

    def split(self, text: str) -> list[str]:
        sentences = self._split_sentences(text)
        if not sentences:
            return []
        distances = self._distances(sentences)
        threshold = self._calculate_threshold(distances)
        pieces: list[str] = []
        start = 0
        for i, distance in enumerate(distances):
            if distance >= threshold:
                pieces.append(" ".join(sentences[start : i + 1]))
                start = i + 1
        pieces.append(" ".join(sentences[start:]))
        return self._enforce_bounds(pieces)

    def chunk(
        self,
        elements: list[LayoutElement],
        *,
        document_id: str,
    ) -> list[DocumentChunk]:
        groups = HeadingAwareChunker._group_by_section(elements)
        result: list[DocumentChunk] = []
        for group in groups:
            body = "\n\n".join(
                e.text.strip() for e in group if e.text.strip() and e.type.lower() != "heading"
            )
            prefix = self._heading_prefix(group)
            full_text = (prefix + "\n\n" + body).strip() if prefix else body
            for part in self.split(full_text):
                result.append(
                    DocumentChunk(
                        id=str(uuid.uuid4()),
                        document_id=document_id,
                        content=part,
                        index=len(result),
                        page_start=min(e.page_number for e in group),
                        page_end=max(e.page_number for e in group),
                        element_ids=[e.id for e in group],
                        bboxes=[e.bbox for e in group if e.bbox],
                        kind="text",
                        section_path=group[0].section_path,
                        token_count=estimate_tokens(part),
                        metadata={"chunker": "semantic"},
                    )
                )
        return result

    @staticmethod
    def _heading_prefix(group: list[LayoutElement]) -> str:
        path = group[0].section_path if group else []
        return "### " + " > ".join(path) if path else ""


class LayoutNormalizer:
    """Bind adjacent captions and footnotes to table/image elements."""

    _caption = re.compile(r"^(?:bảng|table|hình|figure|fig\.?)(?:\s|:|\d)", re.I)
    _footnote = re.compile(r"^(?:ghi chú|note|\(\*\)|\*\s)", re.I)

    @classmethod
    def normalize(cls, elements: list[LayoutElement]) -> list[LayoutElement]:
        result = list(elements)
        consumed: set[int] = set()
        for i, element in enumerate(result):
            if element.type.lower() not in {"table", "image", "figure"}:
                continue
            for j in (i - 1, i + 1):
                if not 0 <= j < len(result) or j in consumed:
                    continue
                candidate = result[j]
                text = candidate.text.strip()
                if cls._caption.match(text) and not element.caption:
                    element.caption = text
                    consumed.add(j)
                elif cls._footnote.match(text):
                    element.metadata.setdefault("footnote", text)
                    consumed.add(j)
        return [e for i, e in enumerate(result) if i not in consumed]

    bind = normalize


class HeadingAwareChunker:
    """Three-lane (text/table/image) chunk router for persisted layouts."""

    @staticmethod
    def _propagate_sections(elements: list[LayoutElement]) -> list[LayoutElement]:
        stack: list[tuple[int, str]] = []
        for e in elements:
            if e.type.lower() == "heading" and e.text.strip():
                level = e.heading_level or 1
                stack = [(l, t) for l, t in stack if l < level]
                stack.append((level, e.text.strip()))
                e.section_path = [t for _, t in stack]
            elif not e.section_path:
                e.section_path = [t for _, t in stack]
        return elements

    @staticmethod
    def _group_by_section(elements: list[LayoutElement]) -> list[list[LayoutElement]]:
        groups: list[list[LayoutElement]] = []
        for e in elements:
            if (
                not groups
                or e.page_number != groups[-1][-1].page_number
                or e.section_path != groups[-1][-1].section_path
            ):
                groups.append([e])
            else:
                groups[-1].append(e)
        return groups

    def __init__(
        self,
        *,
        chunk_size: int = 1200,
        chunk_overlap: int = 200,
        **semantic_options: Any,
    ) -> None:
        self.text = SemanticTextChunker(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            **semantic_options,
        )
        from rag_document_pipeline.chunkers.table import TableChunker

        self.table = TableChunker(chunk_size=chunk_size)
        self.image = ImageChunker()

    def chunk(
        self,
        elements: list[LayoutElement],
        *,
        document_id: str,
    ) -> list[DocumentChunk]:
        elements = self._propagate_sections(elements)
        text: list[LayoutElement] = []
        tables: list[LayoutElement] = []
        images: list[LayoutElement] = []
        for e in elements:
            kind = e.type.lower()
            if kind in {"header", "footer"}:
                continue
            if kind == "table":
                tables.append(e)
            elif kind in {"image", "figure"}:
                images.append(e)
            else:
                text.append(e)
        chunks = (
            self.text.chunk(text, document_id=document_id)
            + self.table.chunk(tables, document_id=document_id)
            + self.image.chunk(images, document_id=document_id)
        )
        chunks.sort(
            key=lambda c: (
                c.page_start,
                c.page_end,
                c.element_ids[0] if c.element_ids else "",
            )
        )
        for i, c in enumerate(chunks):
            c.index = i
        return chunks


class Rechunker:
    """Load layout JSON from storage and produce chunks with new settings."""

    def __init__(self, storage: Any, *, normalizer: Any = LayoutNormalizer) -> None:
        self.storage = storage
        self.normalizer = normalizer

    def rechunk(
        self,
        layout_uri: str,
        *,
        document_id: str,
        chunk_size: int = 1200,
        chunk_overlap: int = 200,
        **options: Any,
    ) -> list[DocumentChunk]:
        raw = self.storage.get(layout_uri)
        data = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
        values = data.get("elements", data) if isinstance(data, dict) else data
        elements = [
            e if isinstance(e, LayoutElement) else LayoutElement.model_validate(e)
            for e in values
        ]
        elements = self.normalizer.normalize(elements)
        return HeadingAwareChunker(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            **options,
        ).chunk(elements, document_id=document_id)

    chunk = rechunk


__all__ = [
    "Rechunker",
    "SemanticTextChunker",
    "HeadingAwareChunker",
    "LayoutNormalizer",
]
