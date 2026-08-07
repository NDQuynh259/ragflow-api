"""Hybrid retrieval (vector + FTS) strategy."""
from typing import Any
from sqlalchemy.orm import Session
from app.storage.vector.pgvector import VectorStoreRepository


class HybridRetriever:
    @staticmethod
    def retrieve(db: Session, query_text: str, query_vector: list[float],
                 top_k: int = 5, document_id: str | None = None) -> list[dict[str, Any]]:
        return VectorStoreRepository.search_hybrid(db, query_text, query_vector, top_k, document_id)
