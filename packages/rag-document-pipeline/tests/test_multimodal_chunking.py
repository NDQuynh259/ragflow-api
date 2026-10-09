from rag_document_pipeline.chunking.multimodal import MultimodalChunker
from rag_document_pipeline.models import ImageData, LayoutElement, TableData


def test_multimodal_router_keeps_large_table_and_image_independent():
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

    kinds = [chunk.kind for chunk in chunks]
    assert kinds[0] == "text"
    assert kinds[-1] == "text"
    assert "table" in kinds
    assert "figure" in kinds
    # The image must remain its own chunk, never merged into a text chunk.
    figure = next(chunk for chunk in chunks if chunk.kind == "figure")
    assert figure.element_ids == ["i1"]
    assert figure.indexable is True
    # Tables must never be merged into text chunks.
    assert all("t1" not in chunk.element_ids for chunk in chunks if chunk.kind == "text")
    assert [chunk.index for chunk in chunks] == list(range(len(chunks)))
    assert chunks[0].section_path == ["Chapter"]


def test_compact_table_is_inline_with_adjacent_text():
    """All tables now route through independent TableChunker, regardless of size."""
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

    assert len(chunks) == 3
    assert chunks[0].kind == "text"
    assert chunks[0].element_ids == ["p1"]
    assert chunks[1].kind == "table"
    assert chunks[1].element_ids == ["t1"]
    assert chunks[2].kind == "text"
    assert chunks[2].element_ids == ["p2"]


def test_textless_image_is_metadata_only():
    element = LayoutElement(
        id="i1",
        type="figure",
        page_number=3,
        bbox=(1, 2, 3, 4),
        image_data=ImageData(uri="images/figure.png"),
    )

    chunk = MultimodalChunker().chunk([element], document_id="doc-3")[0]

    assert chunk.kind == "figure"
    assert chunk.indexable is False
    assert chunk.token_count == 0
    assert chunk.metadata["image_uri"] == "images/figure.png"
    assert chunk.bboxes == [(1, 2, 3, 4)]


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


def test_oversized_single_row_is_split_into_subtables():
    element = LayoutElement(
        id="t1",
        type="table",
        table_data=TableData(headers=["A"], rows=[["y" * 400]]),
    )

    chunks = MultimodalChunker(chunk_size=120).chunk([element], document_id="doc-big-row")

    table_chunks = [c for c in chunks if c.kind == "table"]
    assert len(table_chunks) > 1
    # Every sub-table chunk must stay within chunk_size
    assert all(len(c.content) <= 120 for c in table_chunks)
    # Every chunk must preserve table structure with repeated header
    assert all(c.content.startswith("| A |\n| --- |\n") for c in table_chunks)
    assert all(c.metadata.get("has_repeated_header") is True for c in table_chunks)
    # No oversized_row flag
    assert all("oversized_row" not in c.metadata for c in table_chunks)


def test_oversized_row_with_context_columns_preserved():
    element = LayoutElement(
        id="t2",
        type="table",
        table_data=TableData(
            headers=["Mã", "Điều khoản", "Nội dung"],
            rows=[["HĐ-01", "Bảo mật", "Thông tin bảo mật quan trọng. " * 20]],
        ),
    )

    chunks = MultimodalChunker(chunk_size=200).chunk([element], document_id="doc-ctx")
    table_chunks = [c for c in chunks if c.kind == "table"]
    assert len(table_chunks) > 1
    for c in table_chunks:
        assert len(c.content) <= 200
        # Context columns preserved in each chunk
        assert "HĐ-01" in c.content
        assert "Bảo mật" in c.content
        assert "Mã = HĐ-01" in c.metadata["searchable_text"]
        assert "Điều khoản = Bảo mật" in c.metadata["searchable_text"]


def test_small_table_is_standalone_and_carries_searchable_text():
    """Small tables must be routed to TableChunker and keep searchable_text."""
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

    text_chunks = [c for c in chunks if c.kind == "text"]
    table_chunks = [c for c in chunks if c.kind == "table"]

    assert [c.element_ids for c in text_chunks] == [["p1"]]
    assert len(table_chunks) == 1
    assert table_chunks[0].element_ids == ["small"]
    assert "searchable_text" in table_chunks[0].metadata
    assert "Quarter = Q1" in table_chunks[0].metadata["searchable_text"]
    assert "Revenue = 150" in table_chunks[0].metadata["searchable_text"]


def test_large_table_has_searchable_text_in_standalone_chunks():
    """Large tables split into standalone chunks must each carry searchable_text."""
    element = LayoutElement(
        id="large",
        type="table",
        table_data=TableData(
            headers=["Quarter", "Revenue"],
            rows=[[f"Q{i}", f"{100+i*10}"] for i in range(12)],
            caption="Annual report",
        ),
    )

    chunks = MultimodalChunker(chunk_size=180).chunk([element], document_id="doc-large")
    table_chunks = [chunk for chunk in chunks if chunk.kind == "table"]

    assert table_chunks
    for chunk in table_chunks:
        assert "searchable_text" in chunk.metadata
        assert "Quarter = Q" in chunk.metadata["searchable_text"]
        assert "Revenue = " in chunk.metadata["searchable_text"]
