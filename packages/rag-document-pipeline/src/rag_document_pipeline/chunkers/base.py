"""Base chunker protocol and shared utilities."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from rag_document_pipeline.models import DocumentChunk, LayoutElement


@runtime_checkable
class Chunker(Protocol):
    """Protocol for all chunker implementations."""

    def chunk(
        self,
        elements: list[LayoutElement],
        *,
        document_id: str,
    ) -> list[DocumentChunk]:
        """Split elements into indexable chunks."""
        ...


def estimate_tokens(text: str) -> int:
    """Rough token count — ~4 characters per token for multilingual text."""
    return max(1, len(text) // 4)


def group_by_section(
    elements: list[LayoutElement],
) -> list[list[LayoutElement]]:
    """Gom nhóm các element liền kề có cùng section path và cùng trang."""
    if not elements:
        return []

    groups: list[list[LayoutElement]] = []
    current: list[LayoutElement] = [elements[0]]

    for el in elements[1:]:
        prev = current[-1]
        same_section = el.section_path == prev.section_path
        same_page = el.page_number == prev.page_number
        if same_section and same_page:
            current.append(el)
        else:
            groups.append(current)
            current = [el]
    groups.append(current)
    return groups


__all__ = [
    "Chunker",
    "estimate_tokens",
    "group_by_section",
]
