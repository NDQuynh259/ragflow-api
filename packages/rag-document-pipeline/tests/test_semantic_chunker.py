from rag_document_pipeline.chunking.multimodal import MultimodalChunker
from rag_document_pipeline.chunking.strategies.text import TextChunker
from rag_document_pipeline.models import LayoutElement, TableData


def test_semantic_text_chunker_basic():
    chunker = TextChunker(min_chunk_size=50, max_chunk_size=300)
    elements = [
        LayoutElement(
            id="e1",
            type="heading",
            text="Chương 1: Quy định",
            heading_level=1,
            page_number=1,
        ),
        LayoutElement(
            id="e2",
            type="paragraph",
            text="Nhân viên được nghỉ phép năm 12 ngày hưởng nguyên lương theo luật lao động. "
                 "Trường hợp thâm niên trên 5 năm sẽ được cộng thêm 1 ngày phép hàng năm.",
            page_number=1,
        ),
        LayoutElement(
            id="e3",
            type="paragraph",
            text="Mọi thiết bị laptop công ty cấp phải cài đặt phần mềm diệt virus trước khi kết nối mạng. "
                 "Nghiêm cấm cắm USB không rõ nguồn gốc vào máy tính văn phòng.",
            page_number=1,
        ),
    ]

    chunks = chunker.chunk(elements, document_id="doc_123")
    assert len(chunks) >= 1
    for c in chunks:
        assert c.document_id == "doc_123"
        assert c.kind == "text"
        assert c.metadata["chunker"] == "semantic_hybrid"


def test_multimodal_hybrid_semantic():
    hybrid_chunker = MultimodalChunker(
        min_chunk_size=50,
        max_chunk_size=500,
    )
    elements = [
        LayoutElement(
            id="e1",
            type="heading",
            text="Chương 1: Chính sách",
            heading_level=1,
            page_number=1,
        ),
        LayoutElement(
            id="e2",
            type="paragraph",
            text="Đây là nội dung văn bản đầu tiên của chính sách nhân sự công ty.",
            page_number=1,
        ),
        LayoutElement(
            id="e3",
            type="table",
            text="Bảng phụ cấp",
            table_data=TableData(
                headers=["Cấp bậc", "Phụ cấp"],
                rows=[["Junior", "1.000.000"], ["Senior", "3.000.000"]],
            ),
            page_number=1,
        ),
    ]

    chunks = hybrid_chunker.chunk(elements, document_id="doc_456")
    assert all(c.kind == "text" for c in chunks)

    # Compact tables stay inline with the surrounding text, preserving the header row.
    text_chunk = next(c for c in chunks if "| Cấp bậc | Phụ cấp |" in c.content)
    assert text_chunk.metadata["contains_table"] is True
    assert text_chunk.metadata["table_ids"] == ["e3"]


def test_multimodal_hybrid_semantic_inline():
    """Verify that the multimodal router inlines small tables into text chunks."""
    hybrid_chunker = MultimodalChunker(
        min_chunk_size=50,
        max_chunk_size=500,
    )
    elements = [
        LayoutElement(
            id="e1",
            type="heading",
            text="Chương 1: Chính sách",
            heading_level=1,
            page_number=1,
        ),
        LayoutElement(
            id="e2",
            type="paragraph",
            text="Đây là bảng phụ cấp chi tiết theo từng cấp bậc.",
            page_number=1,
        ),
        LayoutElement(
            id="e3",
            type="table",
            text="Bảng phụ cấp",
            table_data=TableData(
                headers=["Cấp bậc", "Phụ cấp"],
                rows=[["Junior", "1.000.000"], ["Senior", "3.000.000"]],
            ),
            page_number=1,
        ),
    ]

    chunks = hybrid_chunker.chunk(elements, document_id="doc_inline")
    assert len(chunks) >= 1
    # Bảng nhỏ phải được inlined vào content dạng Markdown
    assert any("| Cấp bậc | Phụ cấp |" in c.content for c in chunks)
    assert any(c.metadata.get("contains_table") for c in chunks)


def test_vietnamese_sentence_boundary_detection_abbreviations():
    """Verify abbreviations and numbers are not split prematurely."""
    text = (
        "Trụ sở chính đặt tại TP. Hồ Chí Minh do ThS. Nguyễn Văn A phụ trách. "
        "Tổng kinh phí dự án là 1.500.000 VNĐ (tương đương 1.5% ngân sách quý). "
        "Các tài liệu kèm theo gồm báo cáo, phụ lục, v.v. cần nộp trước ngày 15.10.2026."
    )
    sentences = TextChunker._split_sentences(text)
    # Phải tách thành đúng 3 câu hoàn chỉnh, không bị xé vụn ở TP., ThS., 1.500.000, 1.5%, v.v.
    assert len(sentences) == 3
    assert "TP. Hồ Chí Minh" in sentences[0]
    assert "ThS. Nguyễn Văn A" in sentences[0]
    assert "1.500.000 VNĐ" in sentences[1]
    assert "1.5% ngân sách" in sentences[1]
    assert "v.v." in sentences[2]


def test_vietnamese_sentence_boundary_detection_with_markdown_table():
    """Verify inline markdown tables are kept as atomic blocks and not split by row."""
    text = (
        "Sau đây là bảng tổng hợp doanh số bán hàng của chi nhánh miền Nam:\n\n"
        "| Tháng | Doanh số |\n"
        "| --- | --- |\n"
        "| T1 | 10 tỷ |\n"
        "| T2 | 15 tỷ |\n\n"
        "Kết quả trên cho thấy mức tăng trưởng ổn định trong quý 1."
    )
    sentences = TextChunker._split_sentences(text)
    assert len(sentences) == 3
    # Bảng markdown phải nằm nguyên vẹn trong câu thứ 2
    assert "| Tháng | Doanh số |" in sentences[1]
    assert "| T2 | 15 tỷ |" in sentences[1]
    assert "Kết quả trên cho thấy" in sentences[2]


def test_semantic_topic_shift_detection():
    """Verify that distinct topics are separated at topic shift boundaries."""
    # Đoạn 1 nói về tài chính/doanh thu, đoạn 2 chuyển hẳn sang địa lý/thời tiết
    finance_text = (
        "Doanh thu thuần hợp nhất quý 3 tăng trưởng vượt bậc nhờ mở rộng thị phần. "
        "Lợi nhuận gộp từ hoạt động kinh doanh đạt mức kỷ lục trong năm nay. "
        "Chi phí quản lý doanh nghiệp được tối ưu hóa giúp biên lợi nhuận tăng cao."
    )
    weather_text = (
        "Khí hậu miền Trung chịu ảnh hưởng lớn từ gió mùa đông bắc và áp thấp nhiệt đới. "
        "Lượng mưa trung bình hàng năm tại khu vực vùng núi cao vượt mức bình thường. "
        "Các đợt rét đậm rét hại kéo dài gây ảnh hưởng tiêu cực đến sản xuất nông nghiệp."
    )
    combined = f"{finance_text} {weather_text}"

    chunker = TextChunker(min_chunk_size=100, max_chunk_size=500, threshold_percentile=70.0)
    segments = chunker._split_semantically(combined)

    # Phải nhận diện được điểm chuyển dịch chủ đề và tách thành ít nhất 2 phân đoạn riêng biệt
    assert len(segments) >= 2
    assert "Doanh thu" in segments[0]
    assert any("Khí hậu" in s or "rét đậm" in s for s in segments[1:])


def test_document_pipeline_hybrid_semantic():
    """Verify DocumentPipeline.hybrid_semantic processes elements end-to-end with context prefix."""
    from rag_document_pipeline.pipeline import DocumentPipeline

    class MockParser:
        def parse(self, content: bytes, *, filename: str, image_dir=None):
            return [
                LayoutElement(
                    id="h1",
                    type="heading",
                    text="Chương 1: Khái quát hệ thống",
                    heading_level=1,
                    page_number=1,
                    section_path=["Chương 1: Khái quát hệ thống"],
                ),
                LayoutElement(
                    id="p1",
                    type="paragraph",
                    text="Hệ thống RAG sử dụng hybrid retrieval kết hợp BM25 và Dense Vectors. "
                         "Vector search giúp nắm bắt ngữ nghĩa sâu xa của văn bản.",
                    page_number=1,
                    section_path=["Chương 1: Khái quát hệ thống"],
                ),
            ]

    pipeline = DocumentPipeline.hybrid_semantic(
        parser=MockParser(),
        min_chunk_size=50,
        max_chunk_size=300,
    )
    result = pipeline.process(b"dummy", filename="test.pdf", document_id="doc_sem")
    assert len(result.chunks) >= 1
    assert result.chunks[0].document_id == "doc_sem"
    # Tiền tố context breadcrumb ### Chương 1
    assert "### Chương 1: Khái quát hệ thống" in result.chunks[0].content
    assert result.chunks[0].metadata.get("chunker") == "semantic_hybrid"
