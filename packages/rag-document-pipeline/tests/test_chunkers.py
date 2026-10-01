import pytest
from rag_document_pipeline.chunkers.heading_aware import HeadingAwareChunker
from rag_document_pipeline.chunkers.table import TableChunker
from rag_document_pipeline.models import ImageData, LayoutElement, TableData
from rag_document_pipeline.normalizers.layout import LayoutNormalizer
from rag_document_pipeline.pipeline import DocumentPipeline


def test_caption_and_footnote_binding():
    """Verify that standalone caption and footnote elements are bound to the table."""
    elements = [
        LayoutElement(
            id="c1",
            type="caption",
            text="Bảng 1.1: Doanh thu theo quý năm 2024",
            page_number=1,
        ),
        LayoutElement(
            id="t1",
            type="table",
            text="Bảng doanh thu",
            table_data=TableData(
                headers=["Quý", "Doanh thu (tỷ VNĐ)"],
                rows=[["Q1", "150"], ["Q2", "180"]],
            ),
            page_number=1,
        ),
        LayoutElement(
            id="f1",
            type="footnote",
            text="(*) Số liệu chưa qua kiểm toán độc lập.",
            page_number=1,
        ),
    ]

    normalized = LayoutNormalizer.bind_captions_and_footnotes(elements)

    # Standalone caption and footnote should be absorbed
    assert len(normalized) == 1
    table_el = normalized[0]
    assert table_el.id == "t1"
    assert table_el.caption == "Bảng 1.1: Doanh thu theo quý năm 2024"
    assert table_el.table_data is not None
    assert table_el.table_data.caption == "Bảng 1.1: Doanh thu theo quý năm 2024"
    assert table_el.metadata.get("footnote") == "(*) Số liệu chưa qua kiểm toán độc lập."

    # When rendered to markdown, both caption and footnote are present
    md = TableChunker.render_markdown(table_el)
    assert "### Bảng 1.1: Doanh thu theo quý năm 2024" in md
    assert "| Quý | Doanh thu (tỷ VNĐ) |" in md
    assert "_(*) Số liệu chưa qua kiểm toán độc lập._" in md


def test_figure_caption_binding():
    """Verify that standalone caption below an image is bound to the image element."""
    elements = [
        LayoutElement(
            id="img1",
            type="image",
            image_data=ImageData(uri="figures/chart1.png"),
            page_number=2,
        ),
        LayoutElement(
            id="c2",
            type="paragraph",
            text="Hình 2: Sơ đồ luồng dữ liệu hệ thống RAG",
            page_number=2,
        ),
    ]

    normalized = LayoutNormalizer.bind_captions_and_footnotes(elements)
    assert len(normalized) == 1
    fig_el = normalized[0]
    assert fig_el.id == "img1"
    assert fig_el.caption == "Hình 2: Sơ đồ luồng dữ liệu hệ thống RAG"
    assert fig_el.image_data is not None
    assert fig_el.image_data.caption == "Hình 2: Sơ đồ luồng dữ liệu hệ thống RAG"


def test_semantic_grouping_with_small_table():
    """Verify that a small table is kept inline with its leading text paragraph."""
    chunker = HeadingAwareChunker.hybrid_semantic(
        min_chunk_size=300,
        max_chunk_size=1500,
        semantic_grouping=True,
    )

    elements = [
        LayoutElement(
            id="h1",
            type="heading",
            text="Chương 2: Chính sách phụ cấp",
            heading_level=1,
            page_number=1,
        ),
        LayoutElement(
            id="p1",
            type="paragraph",
            text="Công ty áp dụng các mức phụ cấp chức vụ hàng tháng được quy định chi tiết dưới đây:",
            page_number=1,
        ),
        LayoutElement(
            id="t1",
            type="table",
            table_data=TableData(
                headers=["Chức vụ", "Mức phụ cấp"],
                rows=[["Trưởng phòng", "5.000.000"], ["Phó phòng", "3.000.000"]],
                caption="Bảng phụ cấp chức vụ",
            ),
            page_number=1,
        ),
        LayoutElement(
            id="p2",
            type="paragraph",
            text="Phụ cấp được chi trả cùng kỳ lương hàng tháng vào ngày 05.",
            page_number=1,
        ),
    ]

    chunks = chunker.chunk(elements, document_id="doc_grouping")

    # With semantic grouping, the paragraph and small table within the same section
    # are merged into a unified chunk so context is NOT fragmented.
    assert len(chunks) == 1
    c = chunks[0]
    assert "Chương 2: Chính sách phụ cấp" in c.content
    assert "Công ty áp dụng các mức phụ cấp chức vụ" in c.content
    assert "| Chức vụ | Mức phụ cấp |" in c.content
    assert "Phụ cấp được chi trả cùng kỳ lương" in c.content
    assert "p1" in c.element_ids
    assert "t1" in c.element_ids
    assert "p2" in c.element_ids
    assert c.metadata.get("contains_table") is True


def test_semantic_grouping_with_large_table():
    """Verify that a large table exceeding the small table threshold is chunked by TableChunker."""
    chunker = HeadingAwareChunker(
        chunk_size=300,
        semantic_grouping=True,
    )

    # 15 rows table (large)
    rows = [[f"Mục {i}", f"Giá trị {i}000"] for i in range(15)]
    elements = [
        LayoutElement(
            id="h1",
            type="heading",
            text="Chương 3: Bảng giá vật tư lớn",
            heading_level=1,
            page_number=1,
        ),
        LayoutElement(
            id="p1",
            type="paragraph",
            text="Dưới đây là danh mục toàn bộ vật tư thiết bị:",
            page_number=1,
        ),
        LayoutElement(
            id="t_large",
            type="table",
            table_data=TableData(
                headers=["Tên vật tư", "Đơn giá"],
                rows=rows,
                caption="Bảng giá vật tư toàn diện",
            ),
            page_number=1,
        ),
    ]

    chunks = chunker.chunk(elements, document_id="doc_large")

    # Should produce text chunk for leading paragraph + table chunks with repeated headers
    kinds = [c.kind for c in chunks]
    assert "table" in kinds
    table_chunks = [c for c in chunks if c.kind == "table"]
    assert len(table_chunks) >= 1
    for tc in table_chunks:
        assert "| Tên vật tư | Đơn giá |" in tc.content
        assert tc.section_path == ["Chương 3: Bảng giá vật tư lớn"]


def test_pipeline_normalize_caption_binding():
    """Verify DocumentPipeline._normalize automatically binds captions/footnotes."""
    raw_elements = [
        LayoutElement(
            id="c1",
            type="caption",
            text="Bảng 1: Bảng phân công nhiệm vụ",
            page_number=1,
        ),
        LayoutElement(
            id="t1",
            type="table",
            table_data=TableData(
                headers=["Thành viên", "Nhiệm vụ"],
                rows=[["Nguyễn Văn A", "Backend"], ["Trần Thị B", "Frontend"]],
            ),
            page_number=1,
        ),
        LayoutElement(
            id="fn1",
            type="footnote",
            text="* Thời gian thực hiện: Q4/2024",
            page_number=1,
        ),
    ]

    pipeline = DocumentPipeline()
    normalized = pipeline._normalize(raw_elements)

    # Standalone caption & footnote absorbed into table
    assert len(normalized) == 1
    t = normalized[0]
    assert t.caption == "Bảng 1: Bảng phân công nhiệm vụ"
    assert t.table_data is not None
    assert t.table_data.caption == "Bảng 1: Bảng phân công nhiệm vụ"
    assert t.metadata.get("footnote") == "* Thời gian thực hiện: Q4/2024"
