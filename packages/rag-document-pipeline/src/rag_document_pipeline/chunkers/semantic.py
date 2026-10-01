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

from rag_document_pipeline.chunkers.base import estimate_tokens
from rag_document_pipeline.chunkers.recursive import TextChunker
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
        self._fallback_splitter = TextChunker(
            chunk_size=max_chunk_size,
            chunk_overlap=150,
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
            metadata: dict[str, Any] = {"chunker": "semantic_hybrid"}
            if has_table:
                metadata["contains_table"] = True
                metadata["table_ids"] = [
                    el.id for el in group if el.type.lower() in ("table", "data_table")
                ]

            # Segment the body text semantically
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
        """Extract text representation of an element, rendering tables if needed."""
        if el.type.lower() in ("table", "data_table") and el.table_data:
            from rag_document_pipeline.chunkers.table import TableChunker

            return TableChunker.render_markdown(el)
        return el.text.strip()

    def _split_semantically(self, text: str) -> list[str]:
        """Split text into semantic segments based on topic shift boundaries."""
        sentences = [
            s.strip()
            for s in re.split(r"(?<=[.?!;…\n])\s+", text)
            if s.strip()
        ]
        if len(sentences) <= 1 or len(text) <= self.min_chunk_size:
            return [text]

        # Calculate distances between adjacent sentence buffers
        distances = self._compute_distances(sentences)
        if not distances:
            return [text]

        # Calculate breakpoint threshold based on percentile
        threshold = self._calculate_threshold(distances)

        # Identify split points
        split_indices: list[int] = []
        for idx, dist in enumerate(distances):
            if dist >= threshold:
                split_indices.append(idx + 1)

        # Assemble sentence clusters
        clusters: list[str] = []
        start_idx = 0
        for split_idx in split_indices:
            cluster_text = " ".join(sentences[start_idx:split_idx]).strip()
            if cluster_text:
                clusters.append(cluster_text)
            start_idx = split_idx
        remaining = " ".join(sentences[start_idx:]).strip()
        if remaining:
            clusters.append(remaining)

        # Enforce size bounds (merge small chunks, split huge chunks)
        return self._enforce_bounds(clusters)

    def _compute_distances(self, sentences: list[str]) -> list[float]:
        """Calculate semantic distances between adjacent sentences."""
        n = len(sentences)
        if n < 2:
            return []

        # If embedding function is available, use true vector cosine distance
        if self.embed_fn:
            try:
                embeddings = self.embed_fn(sentences)
                distances: list[float] = []
                for i in range(len(embeddings) - 1):
                    v1, v2 = embeddings[i], embeddings[i + 1]
                    dot = sum(a * b for a, b in zip(v1, v2, strict=False))
                    norm1 = math.sqrt(sum(a * a for a in v1))
                    norm2 = math.sqrt(sum(b * b for b in v2))
                    sim = dot / (norm1 * norm2) if norm1 > 0 and norm2 > 0 else 0.0
                    distances.append(1.0 - max(-1.0, min(1.0, sim)))
                return distances
            except Exception:
                pass  # Fallback to lexical semantic distance

        # Fast lexical-semantic token overlap distance (Zero-cost, works offline)
        tokenized = [set(re.findall(r"\w+", s.lower())) for s in sentences]
        distances = []
        for i in range(len(tokenized) - 1):
            s1, s2 = tokenized[i], tokenized[i + 1]
            if not s1 or not s2:
                distances.append(0.5)
                continue
            intersection = len(s1 & s2)
            union = len(s1 | s2)
            jaccard_sim = intersection / union if union > 0 else 0.0
            distances.append(1.0 - jaccard_sim)
        return distances

    def _calculate_threshold(self, distances: list[float]) -> float:
        """Find the distance threshold at the configured percentile."""
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

    def _enforce_bounds(self, clusters: list[str]) -> list[str]:
        """Merge undersized clusters and split oversized clusters."""
        merged: list[str] = []
        current = ""

        for cluster in clusters:
            if not current:
                current = cluster
            elif len(current) + len(cluster) + 1 <= self.min_chunk_size:
                current = f"{current} {cluster}"
            else:
                merged.append(current)
                current = cluster
        if current:
            merged.append(current)

        # Split clusters exceeding max_chunk_size
        final_segments: list[str] = []
        for seg in merged:
            if len(seg) > self.max_chunk_size:
                final_segments.extend(self._fallback_splitter._splitter.split_text(seg))
            else:
                final_segments.append(seg)

        return final_segments

    @staticmethod
    def _group_by_section(
        elements: list[LayoutElement],
    ) -> list[list[LayoutElement]]:
        """Group adjacent elements sharing the same section path."""
        if not elements:
            return []

        groups: list[list[LayoutElement]] = []
        current: list[LayoutElement] = [elements[0]]

        for el in elements[1:]:
            prev = current[-1]
            same_section = el.section_path == prev.section_path
            same_page = el.page_number == prev.page_number
            if same_section and same_page:
                current.append(el)
            else:
                groups.append(current)
                current = [el]
        groups.append(current)
        return groups

    @staticmethod
    def _heading_prefix(group: list[LayoutElement]) -> str:
        """Extract heading text from the group for context prefix."""
        headings = [el.text.strip() for el in group if el.type == "heading" and el.text.strip()]
        if headings:
            return "## " + " > ".join(headings)
        if group and group[0].section_path:
            return "## " + " > ".join(group[0].section_path)
        return ""
