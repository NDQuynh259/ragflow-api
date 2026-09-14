"""RAG Engine Port interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class RAGEnginePort(ABC):
    """Abstract port for RAG engine interaction."""

    @abstractmethod
    def answer(
        self,
        query: str,
        document_ids: list[str] | None = None,
        top_k: int | None = None,
    ) -> tuple[str, list[dict[str, Any]], dict[str, int]]:
        """Query RAG engine, returning (answer, citations, usage)."""
        pass
