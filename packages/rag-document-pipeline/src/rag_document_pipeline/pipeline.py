from __future__ import annotations

import re
import uuid
from collections import defaultdict

from rag_document_pipeline.models import DocumentChunk, LayoutElement, ProcessedDocument
from rag_document_pipeline.parsers import OpenDataLoaderParser, Parser

CAPTION_RE = re.compile(r"^(?:hình|hinh|figure|fig\.?|sơ đồ|so do|diagram)\b", re.I)
VISUAL_TYPES = {"image", "figure", "shape", "connector", "line", "arrow", "list", "caption"}


class DocumentPipeline:
    """Layout-aware chunking for arbitrary PDF layouts."""

    def __init__(self, parser: Parser | None = None, *, chunk_size: int = 1200, chunk_overlap: int = 200):
        if chunk_size <= 0 or not 0 <= chunk_overlap < chunk_size:
            raise ValueError("Invalid chunk window")
        self.parser = parser or OpenDataLoaderParser()
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def process(self, content: bytes, *, filename: str, document_id: str) -> ProcessedDocument:
        elements = self.parser.parse(content, filename=filename)
        regions = self._find_figure_regions(elements)
        grouped_ids = {element_id for region in regions for element_id in region["ids"]}
        chunks = [self._figure_chunk(document_id, region, i) for i, region in enumerate(regions)]

        for element in elements:
            if element.id in grouped_ids:
                continue
            text = self._clean_text(element.text)
            if not text:
                continue
            kind = "table" if element.type.lower() == "table" else "text"
            step = self.chunk_size - self.chunk_overlap
            for start in range(0, len(text), step):
                value = self._clean_text(text[start:start + self.chunk_size])
                if value:
                    chunks.append(DocumentChunk(
                        id=str(uuid.uuid4()), document_id=document_id, content=value,
                        index=len(chunks), page_start=element.page_number, page_end=element.page_number,
                        element_ids=[element.id], bboxes=[element.bbox] if element.bbox else [],
                        kind=kind, metadata={"element_type": element.type},
                    ))

        chunks.sort(key=lambda chunk: (chunk.page_start, chunk.index))
        for index, chunk in enumerate(chunks):
            chunk.index = index
        return ProcessedDocument(
            document_id=document_id, filename=filename,
            page_count=max((element.page_number for element in elements), default=0),
            elements=elements, chunks=chunks,
        )

    @staticmethod
    def _clean_text(value: str) -> str:
        return re.sub(r"\s+", " ", value or "").strip()

    @classmethod
    def _find_figure_regions(cls, elements: list[LayoutElement]) -> list[dict]:
        by_page: dict[int, list[LayoutElement]] = defaultdict(list)
        for element in elements:
            by_page[element.page_number].append(element)

        regions: list[dict] = []
        for page, page_elements in by_page.items():
            captions = [element for element in page_elements if cls._is_caption(element)]
            for caption in captions:
                candidates = [
                    element for element in page_elements
                    if element.id != caption.id and element.bbox and element.order < caption.order
                    and cls._near_caption(element, caption)
                ]
                # A vector infographic may contain only paragraphs/headings and
                # no element explicitly typed as image/figure.  A caption plus
                # a dense set of nearby positioned elements is still evidence
                # of a visual region, while a lone caption is not.
                visual_signal = any(element.type.lower() in VISUAL_TYPES for element in candidates)
                dense_layout = len(candidates) >= 4
                if not visual_signal and not dense_layout:
                    continue
                region = {"page": page, "caption": caption, "elements": sorted([*candidates, caption], key=lambda e: e.order)}
                region["ids"] = [element.id for element in region["elements"]]
                cls._merge_region(regions, region)

        grouped = {element_id for region in regions for element_id in region["ids"]}
        for element in elements:
            if element.id not in grouped and element.type.lower() in {"image", "figure"} and element.bbox:
                regions.append({"page": element.page_number, "caption": None, "elements": [element], "ids": [element.id]})
        return sorted(regions, key=lambda region: (region["page"], min(e.order for e in region["elements"])))

    @staticmethod
    def _is_caption(element: LayoutElement) -> bool:
        return element.type.lower() in {"caption", "figure_caption"} or bool(CAPTION_RE.match((element.text or "").strip()))

    @staticmethod
    def _near_caption(element: LayoutElement, caption: LayoutElement) -> bool:
        if not element.bbox or not caption.bbox:
            return False
        ey0, ey1, cy0, cy1 = element.bbox[1], element.bbox[3], caption.bbox[1], caption.bbox[3]
        return max(cy0 - ey1, ey0 - cy1, 0) <= 180

    @staticmethod
    def _merge_region(regions: list[dict], region: dict) -> None:
        ids = set(region["ids"])
        for existing in regions:
            if existing["page"] != region["page"] or not ids.intersection(existing["ids"]):
                continue
            merged = {element.id: element for element in [*existing["elements"], *region["elements"]]}
            existing["elements"] = sorted(merged.values(), key=lambda e: e.order)
            existing["ids"] = [element.id for element in existing["elements"]]
            if existing.get("caption") is None:
                existing["caption"] = region.get("caption")
            return
        regions.append(region)

    @classmethod
    def _figure_chunk(cls, document_id: str, region: dict, index: int) -> DocumentChunk:
        elements = region["elements"]
        texts = [cls._clean_text(element.text) for element in elements if cls._clean_text(element.text)]
        content = "[FIGURE]\n" + "\n".join(dict.fromkeys(texts))
        if not texts:
            content += f"\nVisual figure on page {region['page']}"
        return DocumentChunk(
            id=str(uuid.uuid4()), document_id=document_id, content=content, index=index,
            page_start=region["page"], page_end=region["page"], element_ids=region["ids"],
            bboxes=[element.bbox for element in elements if element.bbox],
            kind="diagram" if len(elements) > 1 else "figure", indexable=bool(texts),
            metadata={
                "caption": region["caption"].text if region.get("caption") else None,
                "image_sources": [element.source for element in elements if element.source],
                "element_count": len(elements), "grouping": "caption_geometry",
            },
        )
