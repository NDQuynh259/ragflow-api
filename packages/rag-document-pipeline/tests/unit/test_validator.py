"""Tests for ChunkValidator and IntegrityReport."""

from rag_contracts import DocumentChunk
from rag_document_pipeline.validation import ChunkValidator


def test_validator_token_limit_and_quarantine():
    def simple_token_counter(text: str) -> int:
        return len(text.split())

    validator = ChunkValidator(max_chunk_tokens=5, token_counter=simple_token_counter)

    chunks = [
        DocumentChunk(id="c1", document_id="doc1", content="One two three", index=0),
        DocumentChunk(
            id="c2",
            document_id="doc1",
            content="One two three four five six seven",
            index=1,
        ),
    ]

    valid, report = validator.validate(chunks, document_id="doc1")

    assert len(valid) == 1
    assert valid[0].id == "c1"
    assert "c2" in report.quarantined_chunk_ids
    assert len(report.errors) == 1


def test_validator_repairs_and_coverage():
    validator = ChunkValidator()

    c3 = DocumentChunk(
        id="c3",
        document_id="doc1",
        content="Valid content 3",
        page_start=2,
        page_end=5,
        element_ids=["e3"],
    )
    # Simulate post-creation corruption to verify validator repair
    object.__setattr__(c3, "page_start", 5)
    object.__setattr__(c3, "page_end", 2)

    chunks = [
        # Empty indexable chunk should be dropped
        DocumentChunk(id="empty", document_id="doc1", content="   ", indexable=True),
        # Wrong doc ID should be corrected
        DocumentChunk(id="c1", document_id="wrong_doc", content="Valid content 1", element_ids=["e1"]),
        # Duplicate ID should be reassigned
        DocumentChunk(id="c1", document_id="doc1", content="Valid content 2", element_ids=["e2"]),
        # Swapped page range
        c3,
    ]

    valid, report = validator.validate(
        chunks,
        document_id="doc1",
        input_element_ids={"e1", "e2", "e3", "e4_unrepresented", "e5_filtered"},
        intentionally_filtered_element_ids={"e5_filtered"},
    )

    assert len(valid) == 3
    assert valid[0].document_id == "doc1"
    assert valid[1].id != "c1"  # Reassigned
    assert valid[2].page_start == 2
    assert valid[2].page_end == 5

    assert report.represented_element_count == 3
    assert report.intentionally_filtered_element_ids == ["e5_filtered"]
    assert report.unrepresented_element_ids == ["e4_unrepresented"]
    assert report.coverage_ratio == 4 / 5  # 4 accounted for out of 5
