from rag_document_pipeline.chunking.multimodal import MultimodalChunker
from rag_document_pipeline.models import ImageData, LayoutElement, TableData


def test_multimodal_keeps_table_and_image_as_standalone_chunks():
    """Tables and images retain their own chunk kinds and source provenance."""
    elements = [
        LayoutElement(id="h1", type="heading", text="Chapter", heading_level=1),
        LayoutElement(id="p1", type="paragraph", text="Introductory text.", page_number=1),
        LayoutElement(
            id="t1",
            type="table",
            page_number=1,
            table_data=TableData(
                headers=["Key", "Value"],
                rows=[[str(i), "x" * 50] for i in range(20)],
            ),
        ),
        LayoutElement(
            id="i1",
            type="image",
            page_number=1,
            image_data=ImageData(caption="Architecture diagram"),
        ),
        LayoutElement(id="p2", type="paragraph", text="Closing text.", page_number=1),
    ]

    chunks = MultimodalChunker(chunk_size=180).chunk(elements, document_id="doc-1")

    table_chunks = [chunk for chunk in chunks if chunk.kind == "table"]
    image_chunks = [chunk for chunk in chunks if chunk.kind == "figure"]
    text_chunks = [chunk for chunk in chunks if chunk.kind == "text"]
    assert len(table_chunks) > 1
    assert len(image_chunks) == 1
    assert len(text_chunks) == 2
    assert table_chunks[0].element_ids == ["t1"]
    assert table_chunks[0].page_start == table_chunks[0].page_end == 1
    assert image_chunks[0].element_ids == ["i1"]
    assert "Architecture diagram" in image_chunks[0].content
    assert {chunk.element_ids[0] for chunk in text_chunks} == {"p1", "p2"}
    assert all(chunk.section_path == ["Chapter"] for chunk in chunks)
    assert [chunk.index for chunk in chunks] == list(range(len(chunks)))


def test_compact_table_stays_separate_from_adjacent_text():
    """A compact table is not associated with prose based on adjacency alone."""
    elements = [
        LayoutElement(id="p1", type="paragraph", text="Before table."),
        LayoutElement(
            id="t1",
            type="table",
            table_data=TableData(headers=["A"], rows=[["1"]]),
        ),
        LayoutElement(id="p2", type="paragraph", text="After table."),
    ]

    chunks = MultimodalChunker(chunk_size=500).chunk(elements, document_id="doc-2")

    assert [chunk.kind for chunk in chunks] == ["text", "table", "text"]
    assert [chunk.element_ids for chunk in chunks] == [["p1"], ["t1"], ["p2"]]
    assert "Before table" not in chunks[1].content
    assert "After table" not in chunks[1].content
    assert not chunks[0].metadata.get("related_chunk_ids")
    assert not chunks[1].metadata.get("related_chunk_ids")


def test_explicit_table_reference_links_without_merging_chunks():
    elements = [
        LayoutElement(id="p1", type="paragraph", text="Xem Bảng 2 để biết ngân sách."),
        LayoutElement(
            id="t1",
            type="table",
            caption="Bảng 2: Ngân sách",
            table_data=TableData(headers=["Mục", "Số tiền"], rows=[["A", "100"]]),
        ),
    ]

    chunks = MultimodalChunker().chunk(elements, document_id="doc-link")

    text_chunk, table_chunk = chunks
    assert text_chunk.kind == "text"
    assert table_chunk.kind == "table"
    assert table_chunk.id in text_chunk.metadata["related_chunk_ids"]
    assert text_chunk.id in table_chunk.metadata["related_chunk_ids"]
    assert text_chunk.metadata["association_signal"] == "text_reference"


def test_textless_image_remains_non_indexable_with_provenance():
    """An image without text remains as a non-indexable chunk with its source metadata."""
    element = LayoutElement(
        id="i1",
        type="figure",
        page_number=3,
        bbox=(1, 2, 3, 4),
        image_data=ImageData(uri="images/figure.png"),
    )

    chunks = MultimodalChunker().chunk([element], document_id="doc-3")

    assert len(chunks) == 1
    assert chunks[0].kind == "figure"
    assert chunks[0].element_ids == ["i1"]
    assert chunks[0].page_start == chunks[0].page_end == 3
    assert chunks[0].bboxes == [(1, 2, 3, 4)]
    assert chunks[0].indexable is False
    assert chunks[0].metadata["image_uri"] == "images/figure.png"


def test_split_table_metadata_only_marks_repeated_headers_when_split():
    element = LayoutElement(
        id="t1",
        type="table",
        table_data=TableData(headers=["A"], rows=[["short"]]),
    )
    chunk = MultimodalChunker(chunk_size=500).chunk([element], document_id="doc-4")[0]
    assert "has_repeated_header" not in chunk.metadata


def test_heading_stack_propagation_nests_and_resets():
    elements = [
        LayoutElement(id="h1", type="heading", text="Chapter 1", heading_level=1),
        LayoutElement(id="h2", type="heading", text="Section 1.1", heading_level=2),
        LayoutElement(id="p1", type="paragraph", text="Body one."),
        LayoutElement(id="h3", type="heading", text="Chapter 2", heading_level=1),
        LayoutElement(id="p2", type="paragraph", text="Body two."),
    ]

    chunks = MultimodalChunker().chunk(elements, document_id="doc-h")

    assert chunks[0].section_path == ["Chapter 1", "Section 1.1"]
    assert chunks[1].section_path == ["Chapter 2"]
    assert chunks[0].content.startswith("### Chapter 1 > Section 1.1")


def test_header_footer_are_skipped():
    elements = [
        LayoutElement(id="hd", type="header", text="Company Ltd."),
        LayoutElement(id="p1", type="paragraph", text="Real content."),
        LayoutElement(id="ft", type="footer", text="Page 1"),
    ]

    chunks = MultimodalChunker().chunk(elements, document_id="doc-skip")

    assert len(chunks) == 1
    assert chunks[0].element_ids == ["p1"]
    assert "Company Ltd." not in chunks[0].content
    assert "Page 1" not in chunks[0].content


def test_grouping_respects_page_boundary():
    elements = [
        LayoutElement(id="p1", type="paragraph", text="Page one text.", page_number=1),
        LayoutElement(id="p2", type="paragraph", text="Page two text.", page_number=2),
    ]

    chunks = MultimodalChunker().chunk(elements, document_id="doc-pages")

    assert len(chunks) == 2
    assert chunks[0].page_start == chunks[0].page_end == 1
    assert chunks[1].page_start == chunks[1].page_end == 2


def test_embed_fn_is_used_and_jaccard_fallback_matches_default():
    sentences = "Alpha beta gamma. Alpha beta gamma. Delta epsilon zeta."
    element = LayoutElement(id="p1", type="paragraph", text=sentences)

    calls = {"count": 0}

    def embed_fn(texts):
        calls["count"] += 1
        return [[1.0, 0.0] if "alpha" in t.lower() else [0.0, 1.0] for t in texts]

    with_embed = MultimodalChunker(embed_fn=embed_fn).chunk([element], document_id="d1")
    fallback = MultimodalChunker().chunk([element], document_id="d2")

    assert calls["count"] >= 1
    assert all(chunk.kind == "text" for chunk in with_embed)
    assert all(chunk.kind == "text" for chunk in fallback)


def test_embed_fn_failure_falls_back_to_jaccard():
    def broken_embed(texts):
        raise RuntimeError("provider unavailable")

    element = LayoutElement(id="p1", type="paragraph", text="One two three. Four five six.")

    chunks = MultimodalChunker(embed_fn=broken_embed).chunk([element], document_id="doc-fb")

    assert len(chunks) >= 1
    assert chunks[0].content


def test_oversized_single_row_is_split_into_table_chunks():
    """An oversized single row is split into table chunks with repeated header."""
    element = LayoutElement(
        id="t1",
        type="table",
        table_data=TableData(headers=["A"], rows=[["y" * 400]]),
    )

    chunks = MultimodalChunker(chunk_size=120).chunk([element], document_id="doc-big-row")

    assert len(chunks) > 1
    assert all(chunk.kind == "table" for chunk in chunks)
    assert all(len(chunk.content) <= 120 for chunk in chunks)
    assert all(chunk.element_ids == ["t1"] for chunk in chunks)
    assert all("| A |" in chunk.content for chunk in chunks)


def test_oversized_row_with_context_columns_preserved():
    """Context columns are preserved in each independently indexed table chunk."""
    element = LayoutElement(
        id="t2",
        type="table",
        table_data=TableData(
            headers=["Mã", "Điều khoản", "Nội dung"],
            rows=[["HĐ-01", "Bảo mật", "Thông tin bảo mật quan trọng. " * 20]],
        ),
    )

    chunks = MultimodalChunker(chunk_size=200).chunk([element], document_id="doc-ctx")

    assert all(chunk.kind == "table" for chunk in chunks)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk.content) <= 200
        assert "HĐ-01" in chunk.content
        assert "Bảo mật" in chunk.content
        assert chunk.element_ids == ["t2"]
        assert "HĐ-01" in chunk.metadata["searchable_text"]


def test_small_table_stays_independent_with_searchable_context():
    """A small table remains separate while preserving its searchable text."""
    elements = [
        LayoutElement(id="p1", type="paragraph", text="Revenue context."),
        LayoutElement(
            id="small",
            type="table",
            table_data=TableData(
                headers=["Quarter", "Revenue"],
                rows=[["Q1", "150"]],
                caption="Small table",
            ),
        ),
    ]

    chunks = MultimodalChunker(chunk_size=800).chunk(elements, document_id="doc-inline")

    assert [chunk.kind for chunk in chunks] == ["text", "table"]
    assert chunks[1].element_ids == ["small"]
    assert "Revenue context" not in chunks[1].content
    assert "| Quarter | Revenue |" in chunks[1].content
    assert "Quarter = Q1" in chunks[1].metadata["searchable_text"]


def test_large_table_is_split_with_repeated_headers():
    """A large table is split into standalone chunks, each retaining repeated headers."""
    element = LayoutElement(
        id="large",
        type="table",
        table_data=TableData(
            headers=["Quarter", "Revenue"],
            rows=[[f"Q{i}", f"{100 + i * 10}"] for i in range(12)],
            caption="Annual report",
        ),
    )

    chunks = MultimodalChunker(chunk_size=180).chunk([element], document_id="doc-large")

    assert all(chunk.kind == "table" for chunk in chunks)
    assert len(chunks) > 1
    assert all(chunk.element_ids == ["large"] for chunk in chunks)
    assert all("| Quarter | Revenue |" in chunk.content for chunk in chunks)
    assert all(chunk.metadata["searchable_text"] for chunk in chunks)
