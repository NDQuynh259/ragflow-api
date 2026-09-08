from __future__ import annotations
import re
import uuid
from rag_document_pipeline.models import DocumentChunk, ProcessedDocument
from rag_document_pipeline.parsers import OpenDataLoaderParser, Parser

class DocumentPipeline:
    def __init__(self, parser: Parser | None = None, *, chunk_size: int = 1200, chunk_overlap: int = 200):
        if chunk_size <= 0 or not 0 <= chunk_overlap < chunk_size: raise ValueError("Invalid chunk window")
        self.parser, self.chunk_size, self.chunk_overlap = parser or OpenDataLoaderParser(), chunk_size, chunk_overlap

    def process(self, content: bytes, *, filename: str, document_id: str) -> ProcessedDocument:
        elements = self.parser.parse(content, filename=filename)
        chunks: list[DocumentChunk] = []
        diagram_groups = self._find_diagram_groups(elements)
        grouped_ids = {
            element_id
            for group_ids, _ in diagram_groups.values()
            for element_id in group_ids[1:]
        }
        for element in elements:
            if element.id in grouped_ids:
                continue
            text = element.text.strip()
            if not text:
                if element.type in {"image", "figure"}:
                    group_ids, group_elements = diagram_groups.get(element.id, ([element.id], [element]))
                    diagram_text = "\n".join(item.text.strip() for item in group_elements if item.text.strip())
                    chunks.append(DocumentChunk(
                        id=str(uuid.uuid4()), document_id=document_id,
                        content=element.caption or diagram_text or f"Figure on page {element.page_number}",
                        index=len(chunks), page_start=min(item.page_number for item in group_elements),
                        page_end=max(item.page_number for item in group_elements), element_ids=group_ids,
                        bboxes=[item.bbox for item in group_elements if item.bbox],
                        kind="figure", indexable=bool(element.caption or diagram_text),
                        metadata={"image_source": element.source, "has_caption": bool(element.caption), "diagram_group": group_ids},
                    ))
                continue
            step = self.chunk_size - self.chunk_overlap
            for index, start in enumerate(range(0, len(text), step)):
                value = re.sub(r"\s+", " ", text[start:start+self.chunk_size]).strip()
                if value:
                    chunks.append(DocumentChunk(id=str(uuid.uuid4()), document_id=document_id, content=value, index=len(chunks), page_start=element.page_number, page_end=element.page_number, element_ids=[element.id], bboxes=[element.bbox] if element.bbox else [], kind="table" if element.type == "table" else "text", indexable=True, metadata={"element_type": element.type}))
        return ProcessedDocument(document_id=document_id, filename=filename, page_count=max((e.page_number for e in elements), default=0), elements=elements, chunks=chunks)

    @classmethod
    def _find_diagram_groups(cls, elements):
        """Group an image/icon with nearby heading and text belonging to one diagram."""
        groups = {}
        for image in (e for e in elements if e.type in {"image", "figure"} and e.bbox):
            ix = (image.bbox[0] + image.bbox[2]) / 2
            candidates = [
                e for e in elements
                if e is not image and e.page_number == image.page_number and e.bbox
                and e.type in {"heading", "paragraph", "list", "caption"}
            ]
            related = []
            for e in candidates:
                overlap = min(image.bbox[2], e.bbox[2]) - max(image.bbox[0], e.bbox[0])
                center_in = e.bbox[0] <= ix <= e.bbox[2]
                near = abs(e.bbox[1] - image.bbox[1]) <= 140 or abs(e.bbox[3] - image.bbox[1]) <= 140
                if (overlap > 0 or center_in) and near:
                    related.append(e)
            related.sort(key=lambda e: e.order)
            if related:
                groups[image.id] = ([image.id, *[e.id for e in related]], [image, *related])
        return groups
