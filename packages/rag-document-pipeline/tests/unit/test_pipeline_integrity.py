"""Integration coverage for normalized pipeline output and integrity report."""

import hashlib

from rag_document_pipeline import DocumentPipeline
from rag_document_pipeline.models import LayoutElement


class StaticParser:
    def __init__(self, elements: list[LayoutElement]) -> None:
        self.elements = elements

    def parse(self, content: bytes, *, filename: str, image_dir=None):
        return self.elements


def test_pipeline_exposes_ir_version_provenance_and_coverage_report():
    content = b"same content"
    elements = [
        LayoutElement(id="h1", type="heading", text="Section", order=0),
        LayoutElement(id="p1", type="paragraph", text="Useful source text.", order=1),
        LayoutElement(id="hf", type="header", text="Page header", order=2),
    ]
    pipeline = DocumentPipeline(parser=StaticParser(elements))

    result = pipeline.process(content, filename="sample.txt", document_id="doc-1")

    assert result.integrity_report is not None
    assert result.integrity_report.input_element_count == 3
    assert result.integrity_report.coverage_ratio == 1.0
    assert result.integrity_report.intentionally_filtered_element_ids == ["hf"]
    assert result.integrity_report.contextual_element_ids == ["h1"]
    assert result.chunks[0].metadata["document_version_id"] == hashlib.sha256(content).hexdigest()
    assert result.chunks[0].metadata["source_provenance"]["p1"]["order"] == 1
    assert pipeline.last_integrity_report is result.integrity_report
