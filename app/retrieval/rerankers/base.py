"""Abstract base for rerankers."""
from abc import ABC, abstractmethod
from typing import Any


class BaseReranker(ABC):
    @abstractmethod
    def rerank(self, query: str, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Rerank chunks by relevance to the query."""
        ...
