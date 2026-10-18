"""Integration tests for the full DocumentPipeline with mixed document elements."""

import pytest

from rag_document_pipeline.models import ImageData, LayoutElement, TableData
from rag_document_pipeline.pipeline import DocumentPipeline


class MockParser:
    def __init__(self, elements: list[LayoutElement]) -> None:
        self._elements = elements

    def parse(self, content: bytes, *, filename: str, image_dir=None) -> list[LayoutElement]:
        return list(self._elements)


def test_full_pipeline_mixed_document():
    elements = [
        LayoutElement(id="h1", type="heading", text="Chương I: Quy định chung", heading_level=1, order=0, page_number=1),
        LayoutElement(id="p1", type="paragraph", text="Điều 1. Phạm vi điều chỉnh và đối tượng áp dụng.", order=1, page_number=1),
        LayoutElement(
            id="tbl1",
            type="table",
            text="",
            table_data=TableData(
                headers=["STT", "Chỉ số", "Giá trị"],
                rows=[["1", "Doanh thu", "10 tỷ"]],
            ),
            caption="Bảng 1: Báo cáo tài chính",
            order=2,
            page_number=1,
        ),
        LayoutElement(
            id="img1",
            type="image",
            text="",
            image_data=ImageData(format="png", width=640, height=480, caption="Biểu đồ phân bổ"),
            caption="Biểu đồ phân bổ",
            order=3,
            page_number=2,
        ),
        LayoutElement(id="hf1", type="header", text="Tài liệu lưu hành nội bộ", order=4, page_number=2),
    ]

    pipeline = DocumentPipeline(parser=MockParser(elements))
    content = b"sample pdf binary content"
    result = pipeline.process(content, filename="hop_dong_dich_vu.pdf", document_id="doc-mix-01")

    assert result.document_id == "doc-mix-01"
    assert result.page_count == 2
    assert len(result.chunks) >= 3  # text/heading chunk, table chunk, image chunk

    # Header was filtered
    assert "hf1" in result.integrity_report.intentionally_filtered_element_ids

    # Document type was classified as legal_policy
    assert any(c.metadata.get("document_type") == "legal_policy" for c in result.chunks)

    # Chunks have provenance
    for chunk in result.chunks:
        assert "document_version_id" in chunk.metadata
        assert "source_provenance" in chunk.metadata


def test_full_pipeline_empty_content():
    pipeline = DocumentPipeline(parser=MockParser([]))
    result = pipeline.process(b"", filename="empty.pdf", document_id="doc-empty")

    assert result.document_id == "doc-empty"
    assert len(result.chunks) == 0
    assert result.integrity_report.input_element_count == 0
    assert result.integrity_report.coverage_ratio == 1.0
