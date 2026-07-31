import hashlib
import math
from typing import List
from app.config import settings

class EmbeddingService:
    def __init__(self, provider: str = None):
        self.provider = (provider or settings.EMBEDDING_PROVIDER).lower()
        self.dimension = settings.EMBEDDING_DIMENSION
        if self.provider not in {"openai", "gemini", "mock"}:
            raise ValueError(f"Unsupported embedding provider: {self.provider}")


    # region get_embedding
    def get_embedding(self, text: str) -> List[float]:
        """Generate vector embedding for text using selected provider."""
        if not text or not text.strip():
            return [0.0] * self.dimension

        if self.provider == "openai":
            if not settings.OPENAI_API_KEY:
                raise RuntimeError("OPENAI_API_KEY is required for the OpenAI embedding provider.")
            return self._get_openai_embedding(text)
        if self.provider == "gemini":
            if not settings.GEMINI_API_KEY:
                raise RuntimeError("GEMINI_API_KEY is required for the Gemini embedding provider.")
            return self._get_gemini_embedding(text)
        return self._get_mock_embedding(text)
    

    # region _get_openai_embedding
    def _get_openai_embedding(self, text: str) -> List[float]:
        from openai import OpenAI
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        response = client.embeddings.create(
            input=text,
            model=settings.OPENAI_EMBEDDING_MODEL,
        )
        return self._validate_dimension(list(response.data[0].embedding))
    

    # region _get_gemini_embedding
    def _get_gemini_embedding(self, text: str) -> List[float]:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        response = client.models.embed_content(
            model=settings.GEMINI_EMBEDDING_MODEL,
            contents=text,
            config=types.EmbedContentConfig(output_dimensionality=self.dimension),
        )
        if not response.embeddings:
            raise RuntimeError("Gemini returned no embedding.")
        return self._validate_dimension(list(response.embeddings[0].values))


    # region _validate_dimension
    def _validate_dimension(self, vector: List[float]) -> List[float]:
        if len(vector) != self.dimension:
            raise RuntimeError(
                f"Embedding dimension mismatch: expected {self.dimension}, got {len(vector)}."
            )
        return vector

    #region _get_mock_embedding
    def _get_mock_embedding(self, text: str) -> List[float]:
        """
        Pure Python deterministic normalized vector generator (no numpy required).
        Generates repeatable 1536-dimensional vectors for zero-dependency local testing.
        """
        hash_digest = hashlib.sha256(text.encode("utf-8")).digest()
        raw_vec = []
        for i in range(self.dimension):
            byte_val = hash_digest[i % len(hash_digest)]
            val = ((byte_val + (i * 17)) % 256) / 255.0 - 0.5
            raw_vec.append(val)
        
        # Normalize vector
        magnitude = math.sqrt(sum(v * v for v in raw_vec))
        if magnitude > 0:
            return [v / magnitude for v in raw_vec]
        return raw_vec
