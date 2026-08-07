"""Cross-encoder reranker (future implementation)."""
from typing import Any
from app.retrieval.rerankers.base import BaseReranker


class CrossEncoderReranker(BaseReranker):
    """Rerank using a cross-encoder model."""
    def rerank(self, query: str, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return chunks
