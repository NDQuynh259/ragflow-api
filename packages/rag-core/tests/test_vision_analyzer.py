from __future__ import annotations

from unittest.mock import Mock, patch

from rag_core.providers.ocr.vision import GeminiVisionAnalyzer


def test_vision_analyzer_uses_structured_vietnamese_prompt() -> None:
    response = Mock(text="Loại hình: Biểu đồ cột\nThông điệp chính: tăng trưởng")
    client = Mock()
    client.models.generate_content.return_value = response
    reader = Mock()
    reader._client = client
    reader._read_image.return_value = (b"image-bytes", "image/png")

    with patch("rag_core.providers.ocr.vision.GeminiOCR", return_value=reader):
        analyzer = GeminiVisionAnalyzer(api_key="test-key", model="vision-model")
        result = analyzer("chart.png")

    assert isinstance(result, dict)
    assert result["formatted_text"] == response.text
    request = client.models.generate_content.call_args.kwargs
    assert request["model"] == "vision-model"
    prompt = request["contents"][0].text
    assert "Loại hình" in prompt
    assert "Dữ liệu chi tiết" in prompt
    assert "Không rõ" in prompt
    assert "Do NOT invent numbers" in prompt


def test_vision_analyzer_returns_none_when_provider_fails() -> None:
    client = Mock()
    client.models.generate_content.side_effect = RuntimeError("provider down")
    reader = Mock()
    reader._client = client
    reader._read_image.return_value = (b"image-bytes", "image/png")

    with patch("rag_core.providers.ocr.vision.GeminiOCR", return_value=reader):
        analyzer = GeminiVisionAnalyzer(api_key="test-key")
        assert analyzer("chart.png") is None


def test_vision_analyzer_parses_json_structured_output() -> None:
    import json

    raw_json = json.dumps({
        "image_type": "Biểu đồ cột",
        "title": "Doanh thu năm 2024",
        "main_message": "Doanh thu tăng trưởng 25%",
        "detailed_data": ["Q1: 10 tỷ VNĐ", "Q2: 12.5 tỷ VNĐ"],
        "visible_text": ["Doanh thu", "Năm 2024"],
        "confidence": "high",
    })
    response = Mock(text=raw_json)
    client = Mock()
    client.models.generate_content.return_value = response
    reader = Mock()
    reader._client = client
    reader._read_image.return_value = (b"image-bytes", "image/png")

    with patch("rag_core.providers.ocr.vision.GeminiOCR", return_value=reader):
        analyzer = GeminiVisionAnalyzer(api_key="test-key")
        result = analyzer("chart.png")

    assert isinstance(result, dict)
    assert result["image_type"] == "Biểu đồ cột"
    assert result["title"] == "Doanh thu năm 2024"
    assert result["main_message"] == "Doanh thu tăng trưởng 25%"
    assert result["confidence"] == "high"
    assert len(result["detailed_data"]) == 2
    assert len(result["visible_text"]) == 2

    formatted = result["formatted_text"]
    assert "[IMAGE_ANALYSIS]" in formatted
    assert "Loại hình: Biểu đồ cột" in formatted
    assert "Tiêu đề & Chủ đề: Doanh thu năm 2024" in formatted
    assert "Thông điệp chính: Doanh thu tăng trưởng 25%" in formatted
    assert "- Q1: 10 tỷ VNĐ" in formatted
    assert "- Doanh thu" in formatted

    # Test analyze_text helper
    assert "[IMAGE_ANALYSIS]" in analyzer.analyze_text("chart.png")

    request = client.models.generate_content.call_args.kwargs
    config = request["config"]
    assert config.response_mime_type == "application/json"
    assert config.response_schema is not None


def test_vision_analyzer_analyze_method_returns_model() -> None:
    import json

    raw_json = json.dumps({
        "image_type": "Sơ đồ quy trình",
        "title": "Quy trình thanh toán",
        "main_message": "Gồm 3 bước xác thực",
        "detailed_data": ["Bước 1: Nhập OTP", "Bước 2: Xác nhận"],
        "visible_text": ["OTP", "Xác nhận"],
    })
    response = Mock(text=raw_json)
    client = Mock()
    client.models.generate_content.return_value = response
    reader = Mock()
    reader._client = client
    reader._read_image.return_value = (b"image-bytes", "image/png")

    with patch("rag_core.providers.ocr.vision.GeminiOCR", return_value=reader):
        analyzer = GeminiVisionAnalyzer(api_key="test-key")
        res = analyzer.analyze("flowchart.png")

    assert res is not None
    assert res.image_type == "Sơ đồ quy trình"
    assert res.title == "Quy trình thanh toán"
    assert len(res.detailed_data) == 2
