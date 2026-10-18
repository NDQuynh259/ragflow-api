"""Tests for the normalized IR and public contract compatibility."""

import pytest
from pydantic import ValidationError

from rag_contracts import (
    DocumentChunk,
    DocumentIR,
    ElementIR,
    SectionIR,
    SourceLocation,
)
from rag_contracts.chunks import ChunkRecord


def test_ir_contracts_preserve_optional_values_and_unknown_metadata():
    element = ElementIR(
        element_id="el-1",
        element_type="vendor_custom_type",
        order=0,
        text=None,
        source=SourceLocation(page_number=2, bbox=(1.0, 2.0, 3.0, 4.0)),
        payload={"extra": "kept"},
        confidence=0.75,
    )
    section = SectionIR(section_id="s-1", title="Title", level=1, element_ids=["el-1"])
    document = DocumentIR(
        document_id="doc-1",
        version_id="ver-1",
        elements=[element],
        sections=[section],
        metadata={"source": "user"},
    )

    assert document.elements[0].element_type == "vendor_custom_type"
    assert document.elements[0].payload["extra"] == "kept"
    assert document.sections[0].element_ids == ["el-1"]
    assert DocumentChunk(document_id="doc-1", id="chunk-1", content="ok")
    assert ChunkRecord(document_id="doc-1", id="chunk-2", content="ok")


def test_ir_contracts_reject_invalid_bounds_and_duplicate_element_ids():
    with pytest.raises(ValidationError):
        SourceLocation(page_number=0)
    with pytest.raises(ValidationError):
        ElementIR(element_id="el", order=-1)
    with pytest.raises(ValidationError):
        ElementIR(element_id="el", order=0, confidence=1.1)
    with pytest.raises(ValidationError):
        DocumentIR(
            document_id="doc",
            elements=[
                ElementIR(element_id="duplicate", order=0),
                ElementIR(element_id="duplicate", order=1),
            ],
        )
