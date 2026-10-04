"""Section context propagation and reading-order grouping."""

from __future__ import annotations

from rag_document_pipeline.models import LayoutElement


def propagate_sections(elements: list[LayoutElement]) -> list[LayoutElement]:
    """Propagate the current heading path to elements below each heading."""
    stack: list[tuple[int, str]] = []
    for element in elements:
        if element.type.lower() == "heading" and element.text.strip():
            level = element.heading_level or 1
            stack = [(depth, title) for depth, title in stack if depth < level]
            stack.append((level, element.text.strip()))
            element.section_path = [title for _, title in stack]
        elif not element.section_path and stack:
            element.section_path = [title for _, title in stack]
    return elements


def group_by_section(elements: list[LayoutElement]) -> list[list[LayoutElement]]:
    """Group adjacent elements sharing section path and page number."""
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
