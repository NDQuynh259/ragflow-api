"""Tests for TableProcessor element adapter."""

from rag_document_pipeline.elements import TableProcessor
from rag_document_pipeline.models import LayoutElement, TableData


def test_table_processor_chunking():
    table_data = TableData(
        headers=["Mã", "Tên", "Đơn vị tính", "Đơn giá"],
        rows=[
            ["A01", "Sản phẩm A", "Cái", "100.000"],
            ["B02", "Sản phẩm B", "Hộp", "250.000"],
        ],
    )
    element = LayoutElement(
        id="tbl-1",
        type="table",
        text="",
        table_data=table_data,
        caption="Bảng 1: Báo giá linh kiện",
        page_number=1,
    )

    processor = TableProcessor(chunk_size=1000)
    chunks = processor.chunk([element], document_id="doc-tbl")

    assert len(chunks) >= 1
    assert "Báo giá linh kiện" in chunks[0].content
    assert "Sản phẩm A" in chunks[0].content
    assert chunks[0].kind == "table"
