"""RAG engine adapter connecting to rag-core."""

from __future__ import annotations

import logging
from typing import Any

from chat_api.shared.rag.port import RAGEnginePort

logger = logging.getLogger(__name__)


class RAGEngineAdapter(RAGEnginePort):
    """Adapter bridging Chat API to rag-core RAGEngine."""

    def __init__(self, engine: Any | None = None) -> None:
        self._engine = engine

    def _get_engine(self) -> Any:
        if self._engine is None:
            try:
                from rag_core.engine import RAGEngine
                self._engine = RAGEngine.from_env()
            except Exception as exc:
                logger.warning("Could not initialize live RAGEngine (%s). Operating in fallback mode.", exc)
                return None
        return self._engine

    def answer(
        self,
        query: str,
        document_ids: list[str] | None = None,
        top_k: int | None = None,
    ) -> tuple[str, list[dict[str, Any]], dict[str, int]]:
        engine = self._get_engine()
        if engine is not None:
            try:
                result = engine.answer(query, document_ids=document_ids, top_k=top_k)
                raw_citations = [c.to_dict() for c in result.citations]
                return result.answer, raw_citations, result.usage
            except Exception as exc:
                logger.error("Error executing RAG answer: %s", exc)
                return f"Lỗi khi truy vấn tài liệu: {exc}", [], {}

        # Fallback response when LLM/embedding credentials are not yet configured
        return (
            "Hệ thống RAG chưa được cấu hình API Key (GEMINI_API_KEY). "
            f"Đã nhận câu hỏi: '{query}'. Vui lòng cấu hình file .env để sinh câu trả lời.",
            [],
            {"prompt_tokens": 0, "completion_tokens": 0},
        )


__all__ = ["RAGEngineAdapter"]
