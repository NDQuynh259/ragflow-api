"""OpenAI-specific embedding configuration."""
from app.embeddings.base import EmbeddingService


class OpenAIEmbeddingService(EmbeddingService):
    """OpenAI embedding provider."""
    def __init__(self):
        super().__init__(provider="openai")
