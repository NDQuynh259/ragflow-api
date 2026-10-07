from rag_document_pipeline.chunking.multimodal import MultimodalChunker
from rag_document_pipeline.chunking.strategies.image import ImageChunker
from rag_document_pipeline.chunking.strategies.table import TableChunker
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


def test_small_table_is_inlined_with_adjacent_text():
    """Verify that a small table is kept inline with its leading text paragraph."""
    chunker = MultimodalChunker(
        min_chunk_size=300,
        max_chunk_size=1500,
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

    # The paragraph and small table within the same section are merged into a
    # single text chunk so context is NOT fragmented.
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


def test_large_table_is_chunked_independently():
    """Verify that a large table exceeding the small table threshold is chunked by TableChunker."""
    chunker = MultimodalChunker(
        chunk_size=300,
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
        searchable = tc.metadata.get("searchable_text", "")
        assert "Tên vật tư = Mục" in searchable
        assert "Đơn giá = Giá trị" in searchable
        assert "| --- |" not in searchable


def test_table_searchable_text_preserves_header_value_intersections():
    element = LayoutElement(
        id="t1",
        type="table",
        table_data=TableData(
            headers=["Quý", "Doanh thu", "Lợi nhuận"],
            rows=[["Q1", "150 tỷ", "25 tỷ"]],
            caption="Báo cáo 2024",
        ),
        page_number=1,
    )

    chunk = TableChunker(chunk_size=1000).chunk([element], document_id="doc")[0]

    assert "### Báo cáo 2024" in chunk.content
    assert chunk.metadata["searchable_text"] == (
        "Bảng: Báo cáo 2024\n"
        "Dòng 1: Quý = Q1 | Doanh thu = 150 tỷ | Lợi nhuận = 25 tỷ"
    )


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


def test_image_chunker_ocr_extraction():
    """Verify ImageChunker uses ocr_fn to extract text when no caption is available."""
    called_with = []

    def mock_ocr(path: str) -> str:
        called_with.append(path)
        return "Số hóa đơn: HD-2024-001\nTổng tiền: 5.000.000 VNĐ"

    chunker = ImageChunker(ocr_fn=mock_ocr)
    element = LayoutElement(
        id="img_inv",
        type="image",
        page_number=1,
        image_data=ImageData(uri="documents/invoices/inv_01.png"),
    )

    chunks = chunker.chunk([element], document_id="doc_ocr")
    assert len(chunks) == 1
    c = chunks[0]

    assert c.kind == "figure"
    assert c.indexable is True
    assert c.metadata["has_ocr"] is True
    assert "Số hóa đơn: HD-2024-001" in c.metadata["ocr_text"]
    assert "OCR: Số hóa đơn: HD-2024-001" in c.content
    assert called_with == ["documents/invoices/inv_01.png"]
    assert element.image_data is not None
    assert element.image_data.ocr_text == c.metadata["ocr_text"]


def test_image_chunker_preserves_preexisting_ocr():
    """Verify existing ocr_text is not overwritten and ocr_fn is not invoked unnecessarily."""
    ocr_called = False

    def mock_ocr(path: str) -> str:
        nonlocal ocr_called
        ocr_called = True
        return "New OCR"

    chunker = ImageChunker(ocr_fn=mock_ocr)
    element = LayoutElement(
        id="img_pre",
        type="image",
        page_number=2,
        image_data=ImageData(
            uri="documents/figures/fig.png",
            ocr_text="Đã có văn bản OCR trước đó",
        ),
    )

    chunks = chunker.chunk([element], document_id="doc_ocr_pre")
    assert len(chunks) == 1
    assert not ocr_called
    assert chunks[0].indexable is True
    assert chunks[0].metadata["ocr_text"] == "Đã có văn bản OCR trước đó"
    assert "OCR: Đã có văn bản OCR trước đó" in chunks[0].content


def test_multimodal_chunker_pipeline_ocr_forwarding():
    """Verify ocr_fn is forwarded from DocumentPipeline to MultimodalChunker and ImageChunker."""
    mock_ocr = lambda path: "Bản vẽ thiết kế kỹ thuật - Tỷ lệ 1:100"

    pipeline = DocumentPipeline.hybrid_semantic(ocr_fn=mock_ocr)
    elements = [
        LayoutElement(id="h1", type="heading", text="Hồ sơ thiết kế", heading_level=1),
        LayoutElement(
            id="diag1",
            type="image",
            image_data=ImageData(uri="drawings/cad_01.png"),
        ),
    ]

    # Normalize and chunk
    normalized = pipeline._normalize(elements)
    chunks = pipeline.chunker.chunk(normalized, document_id="doc_pipe_ocr")

    img_chunk = next(c for c in chunks if c.kind == "figure")
    assert img_chunk.indexable is True
    assert img_chunk.metadata.get("has_ocr") is True
    assert "OCR: Bản vẽ thiết kế kỹ thuật - Tỷ lệ 1:100" in img_chunk.content

