"""Embedder protocol and utilities."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Embedder(Protocol):
    """Protocol for embedding providers."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts and return their vector representations."""
        ...

    @property
    def dimension(self) -> int:
        """Dimensionality of the embedding vectors."""
        ...
