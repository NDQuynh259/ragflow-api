"""Generation service — build context, call LLM, parse citations."""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from rag_contracts.chunks import SearchResult
from rag_core.generation.prompts import (
    CONTEXT_TEMPLATE,
    SYSTEM_PROMPT,
    USER_TEMPLATE,
)

logger = logging.getLogger(__name__)


class Citation:
    """A citation linking an answer to a source chunk."""

    def __init__(
        self,
        *,
        document_id: str,
        chunk_id: str,
        page_number: int,
        bbox: tuple[float, float, float, float] | None = None,
        quote: str = "",
    ) -> None:
        self.document_id = document_id
        self.chunk_id = chunk_id
        self.page_number = page_number
        self.bbox = bbox
        self.quote = quote

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "chunk_id": self.chunk_id,
            "page_number": self.page_number,
            "bbox": list(self.bbox) if self.bbox else None,
            "quote": self.quote,
        }


class GenerationResult:
    """Result of RAG generation."""

    def __init__(
        self,
        *,
        answer: str,
        citations: list[Citation] | None = None,
        usage: dict[str, int] | None = None,
    ) -> None:
        self.answer = answer
        self.citations = citations or []
        self.usage = usage or {}


class GenerationService:
    """Generate grounded answers from retrieved context using Gemini LLM.

    Steps:
    1. Build context string from retrieved chunks.
    2. Call Gemini LLM with system + user prompt.
    3. Extract page citations from the response.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self._model = model or os.environ.get("GEMINI_LLM_MODEL", "gemini-2.5-flash")

        if not self._api_key:
            raise ValueError("GEMINI_API_KEY is required for generation.")

        from google import genai

        self._client = genai.Client(api_key=self._api_key)

    def generate(
        self,
        query: str,
        results: list[SearchResult],
    ) -> GenerationResult:
        """Generate an answer grounded in the retrieved chunks."""
        if not results:
            return GenerationResult(answer="Không tìm thấy thông tin phù hợp trong tài liệu.")

        # 1. Build context
        context_parts: list[str] = []
        for i, sr in enumerate(results):
            chunk = sr.chunk
            pages = (
                f"{chunk.page_start}"
                if chunk.page_start == chunk.page_end
                else f"{chunk.page_start}-{chunk.page_end}"
            )
            context_parts.append(
                CONTEXT_TEMPLATE.format(
                    index=i + 1,
                    kind=chunk.kind,
                    pages=pages,
                    content=chunk.content,
                )
            )
        context = "\n".join(context_parts)
        user_message = USER_TEMPLATE.format(context=context, query=query)

        # 2. Call Gemini LLM
        from google.genai import types

        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=user_message,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0.2,
                    max_output_tokens=2048,
                ),
            )
            answer = response.text or ""
        except Exception as exc:
            logger.error("Gemini generation failed: %s", exc)
            return GenerationResult(answer=f"Lỗi khi tạo câu trả lời: {exc}")

        # 3. Extract citations
        citations = self._extract_citations(answer, results)

        # 4. Usage stats
        usage = {}
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            um = response.usage_metadata
            usage = {
                "prompt_tokens": getattr(um, "prompt_token_count", 0) or 0,
                "completion_tokens": getattr(um, "candidates_token_count", 0) or 0,
            }

        return GenerationResult(
            answer=answer,
            citations=citations,
            usage=usage,
        )

    @staticmethod
    def _extract_citations(
        answer: str,
        results: list[SearchResult],
    ) -> list[Citation]:
        """Extract page references from answer and map to source chunks."""
        # Find patterns like [Trang 1], [Trang 2-3], [page 5]
        page_pattern = re.compile(
            r"\[(?:Trang|page|tr\.?|p\.?)\s*(\d+)(?:\s*[-–]\s*(\d+))?\]",
            re.IGNORECASE,
        )
        mentioned_pages: set[int] = set()
        for match in page_pattern.finditer(answer):
            start = int(match.group(1))
            end = int(match.group(2)) if match.group(2) else start
            mentioned_pages.update(range(start, end + 1))

        citations: list[Citation] = []
        seen_chunks: set[str] = set()

        for sr in results:
            chunk = sr.chunk
            chunk_pages = set(range(chunk.page_start, chunk.page_end + 1))
            # If answer mentions pages from this chunk, or no pages mentioned
            # (cite all retrieved chunks)
            if not mentioned_pages or chunk_pages & mentioned_pages:
                if chunk.id not in seen_chunks:
                    seen_chunks.add(chunk.id)
                    bbox = chunk.bboxes[0] if chunk.bboxes else None
                    citations.append(
                        Citation(
                            document_id=chunk.document_id,
                            chunk_id=chunk.id,
                            page_number=chunk.page_start,
                            bbox=bbox,
                        )
                    )

        return citations
