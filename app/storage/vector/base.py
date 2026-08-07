"""Abstract base for vector store adapters."""
from abc import ABC, abstractmethod
from typing import Any


class BaseVectorStore(ABC):
    @abstractmethod
    def add_chunks(self, db, chunks_data: list[dict[str, Any]]) -> int: ...
    @abstractmethod
    def search_vector(self, db, query_vector: list[float], top_k: int = 5,
                      document_id: str | None = None) -> list[dict[str, Any]]: ...
    @abstractmethod
    def search_hybrid(self, db, query_text: str, query_vector: list[float],
                      top_k: int = 5, document_id: str | None = None) -> list[dict[str, Any]]: ...
    @abstractmethod
    def expand_neighbor_chunks(self, db, seed_chunks: list[dict[str, Any]],
                               neighbor_window: int = 1) -> list[dict[str, Any]]: ...
