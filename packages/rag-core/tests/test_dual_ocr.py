from __future__ import annotations

from unittest.mock import Mock

from rag_core.providers.ocr.router import DualOCRRouter


def test_router_returns_fast_ocr_when_result_exceeds_minimum() -> None:
    fast = Mock(return_value="A sufficiently long OCR result with useful text")
    vlm = Mock(return_value="VLM fallback")

    result = DualOCRRouter(fast_ocr=fast, vlm_ocr=vlm)("image.png")

    assert result == "A sufficiently long OCR result with useful text"
    fast.assert_called_once_with("image.png")
    vlm.assert_not_called()


def test_router_falls_back_when_fast_result_is_too_short() -> None:
    fast = Mock(return_value="short")
    vlm = Mock(return_value="Structured VLM result")

    result = DualOCRRouter(fast_ocr=fast, vlm_ocr=vlm, min_text_length=10)("image.png")

    assert result == "Structured VLM result"
    fast.assert_called_once_with("image.png")
    vlm.assert_called_once_with("image.png")


def test_router_falls_back_when_fast_ocr_raises() -> None:
    fast = Mock(side_effect=RuntimeError("tesseract unavailable"))
    vlm = Mock(return_value="VLM recovered")

    result = DualOCRRouter(fast_ocr=fast, vlm_ocr=vlm)("image.png")

    assert result == "VLM recovered"
    vlm.assert_called_once_with("image.png")


def test_router_returns_empty_when_no_provider_is_available() -> None:
    assert DualOCRRouter()("image.png") == ""


def test_router_returns_empty_when_vlm_fails() -> None:
    vlm = Mock(side_effect=RuntimeError("API unavailable"))

    assert DualOCRRouter(vlm_ocr=vlm)("image.png") == ""
