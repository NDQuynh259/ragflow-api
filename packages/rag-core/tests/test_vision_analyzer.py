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

    assert result == response.text
    request = client.models.generate_content.call_args.kwargs
    assert request["model"] == "vision-model"
    prompt = request["contents"][0].text
    assert "Loại hình" in prompt
    assert "Dữ liệu chi tiết" in prompt
    assert "Không rõ" in prompt
    assert "Do NOT invent numbers" in prompt


def test_vision_analyzer_returns_empty_when_provider_fails() -> None:
    client = Mock()
    client.models.generate_content.side_effect = RuntimeError("provider down")
    reader = Mock()
    reader._client = client
    reader._read_image.return_value = (b"image-bytes", "image/png")

    with patch("rag_core.providers.ocr.vision.GeminiOCR", return_value=reader):
        analyzer = GeminiVisionAnalyzer(api_key="test-key")
        assert analyzer("chart.png") == ""
