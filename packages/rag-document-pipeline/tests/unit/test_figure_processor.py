"""Tests for FigureProcessor element adapter."""

from rag_document_pipeline.elements import FigureProcessor
from rag_document_pipeline.models import ImageData, LayoutElement


def test_figure_processor_chunking_with_caption():
    image_data = ImageData(
        format="png",
        width=800,
        height=600,
        caption="Hình 1: Sơ đồ kiến trúc hệ thống",
    )
    element = LayoutElement(
        id="fig-1",
        type="image",
        text="",
        image_data=image_data,
        caption="Hình 1: Sơ đồ kiến trúc hệ thống",
        page_number=2,
    )

    processor = FigureProcessor()
    chunks = processor.chunk([element], document_id="doc-fig")

    assert len(chunks) == 1
    assert "Sơ đồ kiến trúc" in chunks[0].content
    assert chunks[0].kind == "figure"
    assert chunks[0].page_start == 2
