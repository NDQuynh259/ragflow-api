from rag_document_pipeline.chunkers.heading_aware import HeadingAwareChunker
from rag_document_pipeline.chunkers.semantic import SemanticTextChunker
from rag_document_pipeline.models import LayoutElement, TableData


def test_semantic_text_chunker_basic():
    chunker = SemanticTextChunker(min_chunk_size=50, max_chunk_size=300)
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


def test_heading_aware_hybrid_semantic():
    hybrid_chunker = HeadingAwareChunker.hybrid_semantic(min_chunk_size=50, max_chunk_size=500)
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
    kinds = [c.kind for c in chunks]
    assert "text" in kinds
    assert "table" in kinds

    # Verify table has repeated headers
    table_chunk = next(c for c in chunks if c.kind == "table")
    assert "| Cấp bậc | Phụ cấp |" in table_chunk.content
