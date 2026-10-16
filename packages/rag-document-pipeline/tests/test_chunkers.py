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


def test_table_remains_independent_from_surrounding_text():
    """Tables retain their own kind and are not merged with surrounding prose."""
    chunker = MultimodalChunker(chunk_size=1200)

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

    assert [chunk.kind for chunk in chunks] == ["text", "table", "text"]
    assert chunks[1].element_ids == ["t1"]
    assert chunks[1].section_path == ["Chương 2: Chính sách phụ cấp"]
    assert "| Chức vụ | Mức phụ cấp |" in chunks[1].content
    assert "Trưởng phòng" in chunks[1].content
    assert "Công ty áp dụng" in chunks[0].content
    assert "ngày 05" in chunks[2].content


def test_large_table_is_split_into_table_chunks():
    """A large table is split into standalone chunks with repeated headers."""
    chunker = MultimodalChunker(chunk_size=300)

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

    table_chunks = [chunk for chunk in chunks if chunk.kind == "table"]
    assert len(table_chunks) >= 2
    assert all(chunk.element_ids == ["t_large"] for chunk in table_chunks)
    assert all(chunk.section_path == ["Chương 3: Bảng giá vật tư lớn"] for chunk in table_chunks)
    assert all("| Tên vật tư | Đơn giá |" in chunk.content for chunk in table_chunks)


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
        "Bảng: Báo cáo 2024\nDòng 1: Quý = Q1 | Doanh thu = 150 tỷ | Lợi nhuận = 25 tỷ"
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


def test_image_chunker_vision_extraction():
    """Verify ImageChunker uses vision_fn to extract text and description when no caption is available."""
    called_with = []

    def mock_vision(path: str) -> str:
        called_with.append(path)
        return "Số hóa đơn: HD-2024-001\nTổng tiền: 5.000.000 VNĐ"

    chunker = ImageChunker(vision_fn=mock_vision)
    element = LayoutElement(
        id="img_inv",
        type="image",
        page_number=1,
        image_data=ImageData(uri="documents/invoices/inv_01.png"),
    )

    chunks = chunker.chunk([element], document_id="doc_vision")
    assert len(chunks) == 1
    c = chunks[0]

    assert c.kind == "figure"
    assert c.indexable is True
    assert c.metadata["has_vision"] is True
    assert "Số hóa đơn: HD-2024-001" in c.metadata["vision_text"]
    assert "Số hóa đơn: HD-2024-001" in c.content
    assert called_with == ["documents/invoices/inv_01.png"]
    assert element.image_data is not None
    assert element.image_data.description == c.metadata["vision_text"]


def test_image_chunker_preserves_description_and_caption():
    """Verify existing description and caption are preserved in metadata and content."""
    chunker = ImageChunker()
    element = LayoutElement(
        id="img_pre",
        type="image",
        page_number=2,
        image_data=ImageData(
            uri="documents/figures/fig.png",
            caption="Sơ đồ hệ thống",
            description="Mô tả cấu trúc microservices",
        ),
    )

    chunks = chunker.chunk([element], document_id="doc_img_pre")
    assert len(chunks) == 1
    assert chunks[0].indexable is True
    assert "Sơ đồ hệ thống" in chunks[0].content
    assert "Mô tả cấu trúc microservices" in chunks[0].content


def test_multimodal_chunker_pipeline_vision_forwarding():
    """Verify vision_fn is forwarded to the standalone image chunker."""
    mock_vision = lambda path: "Bản vẽ thiết kế kỹ thuật - Tỷ lệ 1:100"

    pipeline = DocumentPipeline.hybrid_semantic(vision_fn=mock_vision)
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
    chunks = pipeline.chunker.chunk(normalized, document_id="doc_pipe_vision")

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.kind == "figure"
    assert chunk.element_ids == ["diag1"]
    assert chunk.section_path == ["Hồ sơ thiết kế"]
    assert "Bản vẽ thiết kế kỹ thuật - Tỷ lệ 1:100" in chunk.content
