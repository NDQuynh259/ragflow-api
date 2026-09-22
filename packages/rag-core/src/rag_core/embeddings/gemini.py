"""Gemini embedding provider using google-genai SDK."""

from __future__ import annotations

import logging
import os
import time

logger = logging.getLogger(__name__)


class GeminiEmbedder:
    """Embed texts using Google Gemini embedding API.

    Uses ``google-genai`` SDK with retry and exponential backoff.
    Configuration is read from environment variables.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        max_retries: int | None = None,
        retry_base_seconds: float | None = None,
        retry_max_seconds: float | None = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self._model = model or os.environ.get("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
        self._max_retries = max_retries or int(os.environ.get("EMBEDDING_MAX_RETRIES", "3"))
        self._retry_base = retry_base_seconds or float(
            os.environ.get("EMBEDDING_RETRY_BASE_SECONDS", "1")
        )
        self._retry_max = retry_max_seconds or float(
            os.environ.get("EMBEDDING_RETRY_MAX_SECONDS", "30")
        )
        self._dimension: int = int(os.environ.get("EMBEDDING_DIMENSION", "768"))

        if not self._api_key:
            raise ValueError("GEMINI_API_KEY is required. Set it in .env or pass api_key=.")

        from google import genai

        self._client = genai.Client(api_key=self._api_key)

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts with retry."""
        if not texts:
            return []

        # Filter empty strings — replace with placeholder to keep alignment
        processed = [t if t.strip() else " " for t in texts]

        from google.genai import types

        embed_config = (
            types.EmbedContentConfig(output_dimensionality=self._dimension)
            if self._dimension
            else None
        )

        for attempt in range(self._max_retries + 1):
            try:
                result = self._client.models.embed_content(
                    model=self._model,
                    contents=processed,
                    config=embed_config,
                )
                # result.embeddings is a list of embedding objects
                vectors = [emb.values for emb in result.embeddings]
                return vectors
            except Exception as exc:
                if attempt >= self._max_retries:
                    logger.error(
                        "Gemini embedding failed after %d retries: %s",
                        self._max_retries,
                        exc,
                    )
                    raise
                wait = min(
                    self._retry_base * (2**attempt),
                    self._retry_max,
                )
                logger.warning(
                    "Gemini embedding attempt %d failed (%s), retrying in %.1fs",
                    attempt + 1,
                    exc,
                    wait,
                )
                time.sleep(wait)

        return []  # unreachable, satisfies type checker
