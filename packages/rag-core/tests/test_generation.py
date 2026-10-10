from __future__ import annotations

from rag_contracts import ChunkRecord, SearchResult
from rag_core.providers.generation.service import GenerationService


def make_result(
    page_start: int,
    page_end: int,
    chunk_id: str = "chunk-1",
    metadata: dict[str, object] | None = None,
) -> SearchResult:
    chunk = ChunkRecord(
        id=chunk_id,
        document_id="doc-1",
        content="nội dung",
        page_start=page_start,
        page_end=page_end,
        metadata=metadata or {},
    )
    return SearchResult(chunk=chunk, score=0.9)


def test_citation_to_dict_includes_image_uri():
    from rag_core.providers.generation.service import Citation

    citation = Citation(
        document_id="doc-1",
        chunk_id="chunk-1",
        page_number=1,
        image_uri="s3://bucket/image.png",
    )

    assert citation.to_dict()["image_uri"] == "s3://bucket/image.png"


def test_extract_citations_maps_mentioned_page():
    service = object.__new__(GenerationService)
    results = [make_result(1, 1), make_result(2, 2, chunk_id="chunk-2")]

    citations = service._extract_citations("Theo [Trang 2] thì...", results)

    assert len(citations) == 1
    assert citations[0].chunk_id == "chunk-2"
    assert citations[0].page_number == 2


def test_extract_citations_cites_all_when_no_page_mentioned():
    service = object.__new__(GenerationService)
    results = [make_result(1, 1), make_result(2, 2, chunk_id="chunk-2")]

    citations = service._extract_citations("Không nêu số trang.", results)

    assert {c.chunk_id for c in citations} == {"chunk-1", "chunk-2"}


def test_extract_citations_carries_image_uri_from_chunk_metadata():
    service = object.__new__(GenerationService)
    result = make_result(
        1,
        1,
        metadata={"image_uri": "s3://bucket/evidence.png"},
    )

    citations = service._extract_citations("[Trang 1]", [result])

    assert citations[0].to_dict()["image_uri"] == "s3://bucket/evidence.png"


def test_extract_citations_handles_non_mapping_chunk_metadata():
    service = object.__new__(GenerationService)
    result = make_result(1, 1, metadata=None)

    citations = service._extract_citations("[Trang 1]", [result])

    assert citations[0].to_dict()["image_uri"] is None


def test_generation_returns_message_without_results():
    service = object.__new__(GenerationService)
    result = service.generate("query", [])
    assert "Không tìm thấy" in result.answer
    assert result.citations == []
