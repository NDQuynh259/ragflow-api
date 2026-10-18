"""Tests for enrichment modules: breadcrumbs, metadata, relationships."""

from rag_contracts import DocumentChunk
from rag_document_pipeline.enrichment import (
    add_bidirectional_relationship,
    preserve_metadata_provenance,
    section_breadcrumb,
)


def test_section_breadcrumb():
    chunk = DocumentChunk(
        id="c1",
        document_id="doc1",
        content="Some text",
        section_path=["Chương I", "Điều 1", "Khoản 2"],
    )
    breadcrumb = section_breadcrumb(chunk)
    assert breadcrumb == "Chương I > Điều 1 > Khoản 2"

    chunk_empty = DocumentChunk(
        id="c2",
        document_id="doc1",
        content="Root text",
        section_path=[],
    )
    assert section_breadcrumb(chunk_empty) == ""


def test_preserve_metadata_provenance():
    meta = {}
    preserve_metadata_provenance(
        meta,
        key="period",
        value="Q2-2026",
        source="regex_extractor",
        confidence=0.9,
    )
    assert meta["period"] == "Q2-2026"
    assert meta["metadata_provenance"]["period"] == {
        "source": "regex_extractor",
        "confidence": 0.9,
    }

    # Second call should not overwrite existing key
    preserve_metadata_provenance(
        meta,
        key="period",
        value="Q3-2026",
        source="other_source",
    )
    assert meta["period"] == "Q2-2026"


def test_add_bidirectional_relationship():
    c1 = DocumentChunk(id="chunk-1", document_id="doc1", content="Text 1")
    c2 = DocumentChunk(id="chunk-2", document_id="doc1", content="Text 2")

    add_bidirectional_relationship(c1, c2)

    assert "chunk-2" in c1.metadata["related_chunk_ids"]
    assert "chunk-1" in c2.metadata["related_chunk_ids"]

    # Calling again does not duplicate IDs
    add_bidirectional_relationship(c1, c2)
    assert c1.metadata["related_chunk_ids"].count("chunk-2") == 1
    assert c2.metadata["related_chunk_ids"].count("chunk-1") == 1
