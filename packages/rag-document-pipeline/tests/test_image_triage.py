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


def test_image_triage_triggers_vision_for_chart() -> None:
    """A chart passing triage invokes vision_fn and retains structured output."""
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

    chunker = ImageChunker(vision_fn=mock_vision)

    element = LayoutElement(
        id="chart_1",
        type="figure",
        page_number=3,
        image_data=ImageData(
            uri="charts/revenue.png",
            caption="Biểu đồ doanh thu 2024",
        ),
        metadata={"width": 800, "height": 600},
    )

    chunks = chunker.chunk([element], document_id="doc_chart")
    assert len(chunks) == 1
    chunk = chunks[0]

    assert chunk.indexable is True
    assert chunk.metadata.get("has_vision") is True
    assert chunk.metadata.get("has_vision_analysis") is True
    assert "Biểu đồ doanh thu 2024" in chunk.content
    assert "[IMAGE_ANALYSIS]" in chunk.content
    mock_vision.assert_called_once_with("charts/revenue.png")


def test_image_chunker_uses_vision_for_scanned_documents() -> None:
    """ImageChunker relies strictly on vision_fn for scanned documents."""
    mock_vision = Mock(
        return_value=(
            "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\n"
            "Độc lập - Tự do - Hạnh phúc\n"
            "HỢP ĐỒNG KINH TẾ SỐ 01/2026/HĐKT\n"
            "Căn cứ Bộ luật Dân sự năm 2015 và nhu cầu của hai bên..."
        )
    )

    chunker = ImageChunker(vision_fn=mock_vision)

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
    assert chunk.metadata.get("has_vision") is True
    assert "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM" in chunk.content
    mock_vision.assert_called_once_with("scans/contract.png")


def test_image_chunker_maps_structured_json_vision_output() -> None:
    """ImageChunker parses standardized JSON dict from vision_fn into chunk metadata & content."""
    mock_json_result = {
        "image_type": "Biểu đồ cột",
        "title": "Doanh thu và Lợi nhuận",
        "main_message": "Doanh thu và lợi nhuận tăng trưởng mạnh qua các quý năm 2020.",
        "detailed_data": [
            "Quý 3/2020: Lợi nhuận gộp 638.29, Doanh thu thuần 1,315.90",
        ],
        "visible_text": [
            "Doanh thu và Lợi nhuận",
            "Quý 3/2020",
        ],
        "confidence": "high",
        "formatted_text": (
            "[IMAGE_ANALYSIS]\n"
            "Loại hình: Biểu đồ cột\n"
            "Tiêu đề & Chủ đề: Doanh thu và Lợi nhuận\n"
            "Thông điệp chính: Doanh thu và lợi nhuận tăng trưởng mạnh qua các quý năm 2020.\n"
            "Độ tin cậy: Cao\n"
            "Dữ liệu chi tiết & Nội dung:\n"
            "- Quý 3/2020: Lợi nhuận gộp 638.29, Doanh thu thuần 1,315.90"
        ),
    }

    mock_vision = Mock(return_value=mock_json_result)
    chunker = ImageChunker(vision_fn=mock_vision)

    element = LayoutElement(
        id="chart_pdr",
        type="figure",
        page_number=2,
        caption="Biểu đồ PDR",
        image_data=ImageData(uri="images/pdr.png"),
        metadata={"width": 800, "height": 600},
    )

    chunks = chunker.chunk([element], document_id="doc_pdr", workspace_id="ws_1")
    assert len(chunks) == 1
    chunk = chunks[0]

    # Kiểm tra metadata cấp 1 đã được bóc tách từ JSON
    assert chunk.metadata["has_vision"] is True
    assert chunk.metadata["has_vision_analysis"] is True
    assert chunk.metadata["image_type"] == "Biểu đồ cột"
    assert chunk.metadata["figure_title"] == "Doanh thu và Lợi nhuận"
    assert chunk.metadata["main_message"] == "Doanh thu và lợi nhuận tăng trưởng mạnh qua các quý năm 2020."
    assert chunk.metadata["confidence"] == "high"
    assert chunk.metadata["detailed_data"] == ["Quý 3/2020: Lợi nhuận gộp 638.29, Doanh thu thuần 1,315.90"]
    assert chunk.metadata["visible_text"] == ["Doanh thu và Lợi nhuận", "Quý 3/2020"]
    assert chunk.metadata["vision_structured"] == mock_json_result

    # Kiểm tra content text proxy
    assert "[IMAGE]" in chunk.content
    assert "Biểu đồ PDR" in chunk.content
    assert "[IMAGE_ANALYSIS]" in chunk.content
    assert "Doanh thu và Lợi nhuận" in chunk.content

    # Kiểm tra ImageData.description được gán thông điệp chính súc tích
    assert element.image_data.description == "Doanh thu và lợi nhuận tăng trưởng mạnh qua các quý năm 2020."

    # Kiểm tra chunk.id tuân thủ chuẩn RFC 9562 UUIDv7
    import uuid
    assert uuid.UUID(chunk.id).version == 7

