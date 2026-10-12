from __future__ import annotations

from unittest.mock import Mock

from rag_document_pipeline.chunking.strategies.image import ImageChunker
from rag_document_pipeline.models import ImageData, LayoutElement


def test_image_triage_skips_small_decorative_images() -> None:
    """Images smaller than min_image_size (100px) must be marked non-indexable."""
    chunker = ImageChunker(min_image_size=100)
    element = LayoutElement(
        id="icon_1",
        type="image",
        page_number=1,
        image_data=ImageData(uri="assets/bullet.png"),
        metadata={"width": 48, "height": 48},
    )

    chunks = chunker.chunk([element], document_id="doc_triage")
    assert len(chunks) == 1
    chunk = chunks[0]

    assert chunk.indexable is False
    assert chunk.metadata["triage_skipped"] is True
    assert chunk.metadata["triage_skip_reason"] == "too_small"
    assert chunk.content == "[IMAGE]"


def test_image_triage_skips_extreme_aspect_ratio_dividers() -> None:
    """Lines or dividers (aspect ratio > 10.0) must be skipped as decorative."""
    chunker = ImageChunker(max_aspect_ratio=10.0)
    element = LayoutElement(
        id="divider_1",
        type="image",
        page_number=1,
        image_data=ImageData(uri="assets/line.png"),
        metadata={"width": 2500, "height": 200},  # aspect ratio 12.5 > 10.0
    )

    chunks = chunker.chunk([element], document_id="doc_triage")
    assert len(chunks) == 1
    chunk = chunks[0]

    assert chunk.indexable is False
    assert chunk.metadata["triage_skipped"] is True
    assert chunk.metadata["triage_skip_reason"] == "extreme_aspect_ratio"


def test_image_triage_triggers_vision_for_large_chart_with_little_ocr() -> None:
    """A chart (>=400px) with little text (<80 chars) must invoke vision_fn and retain structured output."""
    mock_ocr = Mock(return_value="Q1 Q2 Q3")
    mock_vision = Mock(
        return_value=(
            "[IMAGE_ANALYSIS]\n"
            "Loại hình: Biểu đồ cột\n"
            "Tiêu đề: Doanh thu theo quý\n"
            "Thông điệp chính: Doanh thu tăng trưởng mạnh\n"
            "Dữ liệu chi tiết:\n"
            "- Q1: 100 tỷ\n"
            "- Q2: 150 tỷ"
        )
    )

    chunker = ImageChunker(
        ocr_fn=mock_ocr,
        vision_fn=mock_vision,
        vision_min_size=400,
        vision_max_text=80,
    )

    element = LayoutElement(
        id="chart_1",
        type="figure",
        page_number=3,
        image_data=ImageData(uri="charts/revenue.png", caption="Biểu đồ doanh thu 2024"),
        metadata={"width": 800, "height": 600},
    )

    chunks = chunker.chunk([element], document_id="doc_chart")
    assert len(chunks) == 1
    chunk = chunks[0]

    assert chunk.indexable is True
    assert chunk.metadata.get("has_vision") is True
    assert chunk.metadata.get("has_vision_analysis") is True
    assert chunk.metadata.get("has_ocr") is True
    assert chunk.metadata.get("ocr_text") == "Q1 Q2 Q3"
    assert "Biểu đồ doanh thu 2024" in chunk.content
    assert "[IMAGE_ANALYSIS]" in chunk.content
    assert "OCR: [IMAGE_ANALYSIS]" not in chunk.content  # Structured analysis is not mangled with OCR prefix
    mock_ocr.assert_called_once_with("charts/revenue.png")
    mock_vision.assert_called_once_with("charts/revenue.png")


def test_image_chunker_uses_ocr_for_text_heavy_document() -> None:
    """A scanned document with substantial OCR text must not trigger vision_fn."""
    mock_ocr = Mock(
        return_value=(
            "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\n"
            "Độc lập - Tự do - Hạnh phúc\n"
            "HỢP ĐỒNG KINH TẾ SỐ 01/2026/HĐKT\n"
            "Căn cứ Bộ luật Dân sự năm 2015 và nhu cầu của hai bên..."
        )
    )
    mock_vision = Mock()

    chunker = ImageChunker(
        ocr_fn=mock_ocr,
        vision_fn=mock_vision,
        vision_min_size=400,
        vision_max_text=80,
    )

    element = LayoutElement(
        id="scan_1",
        type="image",
        page_number=1,
        image_data=ImageData(uri="scans/contract.png"),
        metadata={"width": 1000, "height": 1400},
    )

    chunks = chunker.chunk([element], document_id="doc_scan")
    assert len(chunks) == 1
    chunk = chunks[0]

    assert chunk.indexable is True
    assert chunk.metadata.get("has_ocr") is True
    assert chunk.metadata.get("has_vision") is not True
    assert "OCR: CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM" in chunk.content
    mock_ocr.assert_called_once_with("scans/contract.png")
    mock_vision.assert_not_called()
