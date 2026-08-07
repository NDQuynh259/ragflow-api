"""Gemini-specific embedding configuration."""
from app.embeddings.base import EmbeddingService


class GeminiEmbeddingService(EmbeddingService):
    """Gemini embedding provider."""
    def __init__(self):
        super().__init__(provider="gemini")
