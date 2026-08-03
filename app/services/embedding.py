import hashlib
import logging
import math
import re
import time
from collections.abc import Callable
from typing import Any

from app.config import settings
from app.core.exceptions import AppError

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(
        self,
        provider: str | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self.provider = (provider or settings.EMBEDDING_PROVIDER).lower()
        self.dimension = settings.EMBEDDING_DIMENSION
        self._client: Any = None
        self._sleep = sleep or time.sleep
        if self.provider not in {"openai", "gemini", "mock"}:
            raise ValueError(f"Unsupported embedding provider: {self.provider}")

    def get_embedding(self, text: str) -> list[float]:
        """Generate a query embedding using the selected provider."""
        if not text or not text.strip():
            return [0.0] * self.dimension

        if self.provider == "mock":
            return self._get_mock_embedding(text)

        client = self._get_client()
        vector = self._run_with_retry(lambda: client.embed_query(text))
        return self._validate_dimension(list(vector))

    def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Generate document embeddings in one provider batch."""
        if not texts:
            return []

        non_empty_positions = [
            index for index, text in enumerate(texts) if text and text.strip()
        ]
        vectors = [[0.0] * self.dimension for _ in texts]
        if not non_empty_positions:
            return vectors

        non_empty_texts = [texts[index] for index in non_empty_positions]
        if self.provider == "mock":
            embedded = [self._get_mock_embedding(text) for text in non_empty_texts]
        else:
            client = self._get_client()
            embedded = [
                self._validate_dimension(list(vector))
                for vector in self._run_with_retry(
                    lambda: client.embed_documents(non_empty_texts)
                )
            ]

        if len(embedded) != len(non_empty_positions):
            raise RuntimeError(
                "Embedding provider returned a different number of vectors than inputs."
            )

        for position, vector in zip(non_empty_positions, embedded, strict=True):
            vectors[position] = vector
        return vectors

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client

        if self.provider == "openai":
            if not settings.OPENAI_API_KEY:
                raise RuntimeError(
                    "OPENAI_API_KEY is required for the OpenAI embedding provider."
                )
            from langchain_openai import OpenAIEmbeddings

            self._client = OpenAIEmbeddings(
                api_key=settings.OPENAI_API_KEY,
                model=settings.OPENAI_EMBEDDING_MODEL,
                dimensions=self.dimension,
            )
        elif self.provider == "gemini":
            if not settings.GEMINI_API_KEY:
                raise RuntimeError(
                    "GEMINI_API_KEY is required for the Gemini embedding provider."
                )
            from langchain_google_genai import GoogleGenerativeAIEmbeddings

            self._client = GoogleGenerativeAIEmbeddings(
                google_api_key=settings.GEMINI_API_KEY,
                model=settings.GEMINI_EMBEDDING_MODEL,
                output_dimensionality=self.dimension,
            )
        else:
            raise RuntimeError("The mock embedding provider does not use a client.")
        return self._client

    def _run_with_retry(self, operation: Callable[[], Any]) -> Any:
        """Retry temporary provider rate limits, then expose a safe HTTP 429."""
        for attempt in range(settings.EMBEDDING_MAX_RETRIES + 1):
            try:
                return operation()
            except Exception as exc:
                if not self._is_rate_limit_error(exc):
                    raise

                retry_after = self._retry_after_seconds(exc, attempt)
                if attempt >= settings.EMBEDDING_MAX_RETRIES:
                    raise self._quota_error(retry_after) from exc

                logger.warning(
                    "%s embedding quota exceeded; retrying in %.2f seconds (%d/%d).",
                    self.provider,
                    retry_after,
                    attempt + 1,
                    settings.EMBEDDING_MAX_RETRIES,
                )
                self._sleep(retry_after)

        raise RuntimeError("Embedding retry loop exited unexpectedly.")

    @staticmethod
    def _exception_chain(exc: Exception):
        seen: set[int] = set()
        current: BaseException | None = exc
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            yield current
            current = current.__cause__ or current.__context__

    @classmethod
    def _is_rate_limit_error(cls, exc: Exception) -> bool:
        for current in cls._exception_chain(exc):
            status_code = getattr(current, "status_code", None)
            response = getattr(current, "response", None)
            response_status = getattr(response, "status_code", None)
            if status_code == 429 or response_status == 429:
                return True

            message = str(current).lower()
            if "resource_exhausted" in message:
                return True
            if "429" in message and ("quota" in message or "rate limit" in message):
                return True
        return False

    @classmethod
    def _retry_after_seconds(cls, exc: Exception, attempt: int) -> float:
        delays: list[float] = []
        patterns = (
            r"retry\s+in\s+([0-9]+(?:\.[0-9]+)?)s",
            r"retryDelay['\"]?\s*:\s*['\"]([0-9]+(?:\.[0-9]+)?)s",
        )
        for current in cls._exception_chain(exc):
            response = getattr(current, "response", None)
            headers = getattr(response, "headers", None)
            if headers:
                retry_header = headers.get("retry-after")
                try:
                    if retry_header is not None:
                        delays.append(float(retry_header))
                except (TypeError, ValueError):
                    pass

            message = str(current)
            for pattern in patterns:
                delays.extend(float(value) for value in re.findall(pattern, message, re.I))

        fallback = settings.EMBEDDING_RETRY_BASE_SECONDS * (2**attempt)
        delay = max(delays) if delays else fallback
        return min(delay, settings.EMBEDDING_RETRY_MAX_SECONDS)

    def _quota_error(self, retry_after: float) -> AppError:
        retry_after_header = str(max(0, math.ceil(retry_after)))
        provider_name = "Gemini" if self.provider == "gemini" else "OpenAI"
        return AppError(
            f"{provider_name} embedding quota was exceeded. "
            f"Retry after {retry_after_header} seconds. If this continues, review "
            "the provider quota/billing or select a different EMBEDDING_PROVIDER.",
            status_code=429,
            headers={"Retry-After": retry_after_header},
        )

    def _validate_dimension(self, vector: list[float]) -> list[float]:
        if len(vector) != self.dimension:
            raise RuntimeError(
                f"Embedding dimension mismatch: expected {self.dimension}, got {len(vector)}."
            )
        return vector

    def _get_mock_embedding(self, text: str) -> list[float]:
        """Generate a deterministic normalized vector for local testing."""
        hash_digest = hashlib.sha256(text.encode("utf-8")).digest()
        raw_vec = []
        for index in range(self.dimension):
            byte_val = hash_digest[index % len(hash_digest)]
            value = ((byte_val + (index * 17)) % 256) / 255.0 - 0.5
            raw_vec.append(value)

        magnitude = math.sqrt(sum(value * value for value in raw_vec))
        if magnitude > 0:
            return [value / magnitude for value in raw_vec]
        return raw_vec
