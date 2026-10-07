"""Embedding provider implementations."""

from .gemini import GeminiEmbedder

# NOTE: cohere.py / mock.py / openai.py are still TODO stubs.
# Export them here once their classes are implemented, otherwise importing
# this package (e.g. RAGEngine.from_env) raises ImportError.

__all__ = [
    "GeminiEmbedder",
]
