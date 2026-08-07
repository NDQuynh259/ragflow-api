"""OpenAI-specific LLM configuration."""
from app.generation.llm.base import LLMService


class OpenAILLM(LLMService):
    """OpenAI LLM provider."""
    def __init__(self):
        super().__init__(provider="openai")
