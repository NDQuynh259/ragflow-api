"""Gemini-specific LLM configuration."""
from app.generation.llm.base import LLMService


class GeminiLLM(LLMService):
    """Gemini LLM provider."""
    def __init__(self):
        super().__init__(provider="gemini")
