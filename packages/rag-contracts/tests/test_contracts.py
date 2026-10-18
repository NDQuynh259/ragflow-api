"""Unit tests for rag-contracts models."""

import pytest
from pydantic import ValidationError

from rag_contracts import (
    DocumentChunk,
    DocumentIR,
    ElementIR,
    ElementType,
    ImageData,
    LayoutElement,
    SectionIR,
    SourceLocation,
    TableData,
)


def test_source_location_and_element_ir():
    loc = SourceLocation(page_number=1, bbox=(0.0, 10.0, 100.0, 50.0), source_element_id="el-1")
    element = ElementIR(
        element_id="el-1",
        element_type="paragraph",
        order=0,
        text="Hello world",
        source=loc,
        payload={"custom": "val"},
        confidence=0.95,
    )
    assert element.element_id == "el-1"
    assert element.source.page_number == 1
    assert element.confidence == 0.95


def test_document_ir_validation():
    el1 = ElementIR(element_id="el-1", order=0, text="Intro")
    el2 = ElementIR(element_id="el-2", order=1, text="Body")
    sec1 = SectionIR(
        section_id="sec-1",
        title="Introduction",
        level=1,
        element_ids=["el-1", "el-2"],
        section_path=["Introduction"],
    )

    doc = DocumentIR(
        document_id="doc-123",
        version_id="v1",
        title="Doc Title",
        elements=[el1, el2],
        sections=[sec1],
    )
    assert doc.document_id == "doc-123"
    assert len(doc.elements) == 2
    assert len(doc.sections) == 1

    # Duplicate element IDs should fail
    with pytest.raises(ValidationError):
        DocumentIR(
            document_id="doc-dup",
            elements=[el1, el1],
            sections=[],
        )

    # Section referring to non-existent element should fail
    with pytest.raises(ValidationError):
        DocumentIR(
            document_id="doc-invalid-ref",
            elements=[el1],
            sections=[
                SectionIR(section_id="s1", element_ids=["non-existent"]),
            ],
        )


def test_backward_compatibility_contracts():
    chunk = DocumentChunk(
        id="c-1",
        document_id="d-1",
        content="Chunk content",
        chunk_type="text",
        index=0,
    )
    assert chunk.id == "c-1"

    layout_el = LayoutElement(
        id="le-1",
        type=ElementType.PARAGRAPH,
        text="Sample paragraph",
        page_number=1,
    )
    assert layout_el.type == ElementType.PARAGRAPH
