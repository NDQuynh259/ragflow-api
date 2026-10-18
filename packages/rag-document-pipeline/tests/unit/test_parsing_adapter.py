"""Tests for parser-to-IR conversion."""

from rag_document_pipeline.models import LayoutElement
from rag_document_pipeline.parsing.adapter import document_ir_from_elements


def test_adapter_preserves_order_sources_sections_and_payload():
    elements = [
        LayoutElement(id="h1", type="heading", text="Chapter", heading_level=1, order=0),
        LayoutElement(
            id="p1",
            type="paragraph",
            text="Body",
            order=1,
            page_number=3,
            bbox=(1, 2, 3, 4),
            metadata={"raw_type": "paragraph", "confidence": 0.9},
        ),
    ]

    document = document_ir_from_elements(
        elements,
        document_id="doc-1",
        version_id="v1",
        document_type="internal",
    )

    body = next(element for element in document.elements if element.element_id == "p1")
    assert body.order == 1
    assert body.source.page_number == 3
    assert body.source.bbox == (1.0, 2.0, 3.0, 4.0)
    assert body.parent_section_id is not None
    assert document.sections[0].section_path == ["Chapter"]
