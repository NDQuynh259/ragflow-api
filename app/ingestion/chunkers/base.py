"""Abstract base for text chunkers."""
from abc import ABC, abstractmethod
from typing import Any


class BaseChunker(ABC):
    @abstractmethod
    def split(self, text: str, chunk_size: int = 1200, chunk_overlap: int = 200) -> list[dict[str, Any]]:
        """Split text into overlapping chunks."""
        ...
