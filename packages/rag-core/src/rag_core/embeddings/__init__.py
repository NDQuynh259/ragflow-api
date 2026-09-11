"""Embedding providers."""

from .base import Embedder
from .gemini import GeminiEmbedder

__all__ = ["Embedder", "GeminiEmbedder"]
