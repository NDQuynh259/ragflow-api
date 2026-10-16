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
    """Group adjacent elements sharing section path and page."""
    if not elements:
        return []
    groups: list[list[LayoutElement]] = [[elements[0]]]
    for element in elements[1:]:
        previous = groups[-1][-1]
        if element.section_path == previous.section_path and element.page_number == previous.page_number:
            groups[-1].append(element)
        else:
            groups.append([element])
    return groups
