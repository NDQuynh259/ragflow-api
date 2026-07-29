"""Retrieval use cases shared by search and chat."""

from sqlalchemy.orm import Session

from app.dto import SearchQueryRequest, SearchQueryResponse, SearchResultChunk
from app.repositories.vector_store_repository import VectorStoreRepository
from app.services.embedding import EmbeddingService


class RetrievalService:
    def __init__(self, embedder: EmbeddingService | None = None) -> None:
        self.embedder = embedder or EmbeddingService()

    def retrieve(self, db: Session, request: SearchQueryRequest) -> list[dict]:
        query_vector = self.embedder.get_embedding(request.query)
        if request.search_type == "vector":
            return VectorStoreRepository.search_vector(
                db, query_vector, request.top_k, request.document_id
            )
        return VectorStoreRepository.search_hybrid(
            db, request.query, query_vector, request.top_k, request.document_id
        )

    def search(self, db: Session, request: SearchQueryRequest) -> SearchQueryResponse:
        results = self.retrieve(db, request)
        return SearchQueryResponse(
            query=request.query,
            top_k=request.top_k,
            search_type=request.search_type,
            results=[SearchResultChunk(**result) for result in results],
        )
