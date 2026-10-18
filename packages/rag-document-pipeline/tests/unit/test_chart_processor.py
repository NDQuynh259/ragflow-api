"""Tests for chart fallback and provenance-aware processing."""

from rag_document_pipeline.chunking.multimodal import MultimodalChunker
from rag_document_pipeline.elements.chart import ChartProcessor
from rag_document_pipeline.models import ImageData, LayoutElement


def test_chart_processor_uses_figure_path_without_claiming_extracted_values():
    chart = LayoutElement(
        id="chart-1",
        type="chart",
        page_number=2,
        caption="Revenue trend",
        image_data=ImageData(uri="charts/revenue.png"),
    )
    chunks = ChartProcessor().chunk(chart, document_id="doc-1")

    assert len(chunks) == 1
    assert chunks[0].kind == "figure"
    assert chunks[0].metadata["image_uri"] == "charts/revenue.png"


def test_router_marks_chart_as_figure_fallback():
    chart = LayoutElement(
        id="chart-2",
        type="chart",
        page_number=1,
        caption="Quarterly revenue",
        image_data=ImageData(uri="charts/q.png"),
    )

    chunk = MultimodalChunker().chunk([chart], document_id="doc-2")[0]

    assert chunk.kind == "figure"
    assert chunk.metadata["modality"] == "chart"
    assert chunk.metadata["chart_processing"] == "figure_fallback"
