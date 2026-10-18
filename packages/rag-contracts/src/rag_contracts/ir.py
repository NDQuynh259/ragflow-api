"""Normalized intermediate-representation contracts for parsed documents."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class SourceLocation(BaseModel):
    """Source coordinates and parser identity for a normalized element."""

    page_number: int | None = Field(default=None, ge=1)
    bbox: tuple[float, float, float, float] | None = None
    source_element_id: str | None = None


class ElementIR(BaseModel):
    """Parser-neutral representation of one ordered document element."""

    element_id: str
    element_type: str = "unknown"
    order: int = Field(ge=0)
    text: str | None = None
    parent_section_id: str | None = None
    source: SourceLocation = Field(default_factory=SourceLocation)
    payload: dict[str, Any] = Field(default_factory=dict)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class SectionIR(BaseModel):
    """A heading-derived section and its directly assigned elements."""

    section_id: str
    title: str | None = None
    level: int | None = Field(default=None, ge=1)
    parent_section_id: str | None = None
    element_ids: list[str] = Field(default_factory=list)
    section_path: list[str] = Field(default_factory=list)


class DocumentIR(BaseModel):
    """Normalized document representation shared by pipeline stages."""

    document_id: str
    version_id: str | None = None
    title: str | None = None
    document_type: str | None = None
    elements: list[ElementIR] = Field(default_factory=list)
    sections: list[SectionIR] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _element_ids_are_unique(self) -> DocumentIR:
        element_ids = [element.element_id for element in self.elements]
        if len(element_ids) != len(set(element_ids)):
            raise ValueError("element_id values must be unique within a document")
        section_ids = [section.section_id for section in self.sections]
        if len(section_ids) != len(set(section_ids)):
            raise ValueError("section_id values must be unique within a document")
        element_id_set = set(element_ids)
        for section in self.sections:
            if not set(section.element_ids).issubset(element_id_set):
                raise ValueError("section element_ids must refer to document elements")
        return self


__all__ = ["DocumentIR", "ElementIR", "SectionIR", "SourceLocation"]
