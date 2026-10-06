"""Gemini embedding provider using google-genai SDK."""

from __future__ import annotations

import logging
import os
import re
import time

logger = logging.getLogger(__name__)


class GeminiEmbedder:
    """Embed texts using Google Gemini embedding API.

    Uses ``google-genai`` SDK with retry, rate-limit awareness (429), and backoff.
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
        retry_429_seconds: float | None = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self._model = model or os.environ.get("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
        self._max_retries = max_retries or int(os.environ.get("EMBEDDING_MAX_RETRIES", "3"))
        self._retry_base = retry_base_seconds or float(
            os.environ.get("EMBEDDING_RETRY_BASE_SECONDS", "1")
        )
        self._retry_max = retry_max_seconds or float(
            os.environ.get("EMBEDDING_RETRY_MAX_SECONDS", "60")
        )
        self._retry_429_seconds = retry_429_seconds or float(
            os.environ.get("EMBEDDING_RETRY_429_SECONDS", "15")
        )
        self._dimension: int = int(os.environ.get("EMBEDDING_DIMENSION", "768"))

        if not self._api_key:
            raise ValueError("GEMINI_API_KEY is required. Set it in .env or pass api_key=.")

        from google import genai

        self._client = genai.Client(api_key=self._api_key)

    @property
    def dimension(self) -> int:
        return self._dimension

    def _extract_retry_delay(self, exc: Exception) -> float | None:
        """Extract recommended retry delay (in seconds) from Gemini API response or error details."""
        # 1. Check HTTP response headers (Retry-After)
        response = getattr(exc, "response", None)
        if response is not None and hasattr(response, "headers"):
            retry_after = response.headers.get("retry-after") or response.headers.get("Retry-After")
            if retry_after:
                try:
                    return float(retry_after)
                except ValueError:
                    pass

        # 2. Check error details dict for RetryInfo (Google RPC standard: RetryInfo.retryDelay)
        details = getattr(exc, "details", None)
        if isinstance(details, dict):
            rpc_details = details.get("error", {}).get("details", [])
            if isinstance(rpc_details, list):
                for item in rpc_details:
                    if isinstance(item, dict) and "retryDelay" in item:
                        delay_str = str(item["retryDelay"]).rstrip("s")
                        try:
                            return float(delay_str)
                        except ValueError:
                            pass

        # 3. Regex match from error message or string representation
        exc_str = str(exc)
        # Matches Google message: "Please retry in 25.417930411s."
        m = re.search(r"retry in\s+(\d+(?:\.\d+)?)s", exc_str, re.IGNORECASE)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                pass

        # Matches serialized RPC: 'retryDelay': '25s'
        m2 = re.search(r"['\"]retryDelay['\"]\s*:\s*['\"](\d+(?:\.\d+)?)s?['\"]", exc_str, re.IGNORECASE)
        if m2:
            try:
                return float(m2.group(1))
            except ValueError:
                pass

        return None

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts with retry and intelligent 429 rate-limit handling."""
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
                embeddings = result.embeddings or []
                vectors: list[list[float]] = [
                    list(emb.values) if emb.values is not None else []
                    for emb in embeddings
                ]
                return vectors
            except Exception as exc:
                if attempt >= self._max_retries:
                    logger.error(
                        "Gemini embedding failed after %d retries: %s",
                        self._max_retries,
                        exc,
                    )
                    raise

                # Check if rate-limited (HTTP 429 / RESOURCE_EXHAUSTED)
                is_rate_limited = (
                    getattr(exc, "code", None) == 429
                    or "429" in str(exc)
                    or "RESOURCE_EXHAUSTED" in str(exc)
                )

                retry_delay = self._extract_retry_delay(exc)
                if retry_delay is not None:
                    # Respect Google's recommended wait + 0.5s safety buffer
                    wait = min(retry_delay + 0.5, self._retry_max)
                    logger.warning(
                        "Gemini embedding rate-limited (attempt %d). Google requested wait %.1fs (sleeping %.1fs)",
                        attempt + 1,
                        retry_delay,
                        wait,
                    )
                elif is_rate_limited:
                    # 429 without explicit delay -> use configured 429 backoff
                    wait = min(self._retry_429_seconds * (1.5**attempt), self._retry_max)
                    logger.warning(
                        "Gemini embedding rate-limited (attempt %d). Backing off for %.1fs (EMBEDDING_RETRY_429_SECONDS)",
                        attempt + 1,
                        wait,
                    )
                else:
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

