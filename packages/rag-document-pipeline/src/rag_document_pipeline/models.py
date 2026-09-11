from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ElementType(str, Enum):
    """Canonical element types produced by document parsers."""

    TEXT = "text"
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST = "list"
    TABLE = "table"
    IMAGE = "image"
    FIGURE = "figure"
    CAPTION = "caption"
    FORMULA = "formula"
    HEADER = "header"
    FOOTER = "footer"


# ---------------------------------------------------------------------------
# Sub-models for structured element data
# ---------------------------------------------------------------------------

class TableData(BaseModel):
    """Structured table content extracted by the parser."""

    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    row_start: int = 0
    row_end: int | None = None
    caption: str | None = None


class ImageData(BaseModel):
    """Metadata for an image/figure extracted by the parser."""

    uri: str | None = None
    caption: str | None = None
    description: str | None = None
    ocr_text: str | None = None
    caption_refs: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Core layout element — output of a parser adapter
# ---------------------------------------------------------------------------

class LayoutElement(BaseModel):
    id: str
    type: str
    text: str = ""
    page_number: int = 1
    bbox: tuple[float, float, float, float] | None = None
    source: str | None = None
    caption: str | None = None
    order: int = 0
    heading_level: int | None = None
    section_path: list[str] = Field(default_factory=list)
    table_data: TableData | None = None
    image_data: ImageData | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Document chunk — output of a chunker
# ---------------------------------------------------------------------------

class DocumentChunk(BaseModel):
    id: str
    document_id: str
    content: str
    index: int
    page_start: int
    page_end: int
    element_ids: list[str] = Field(default_factory=list)
    bboxes: list[tuple[float, float, float, float]] = Field(default_factory=list)
    kind: str = "text"
    section_path: list[str] = Field(default_factory=list)
    token_count: int = 0
    indexable: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Pipeline outputs
# ---------------------------------------------------------------------------

class ProcessedDocument(BaseModel):
    """Final output of the document pipeline."""

    document_id: str
    filename: str
    page_count: int
    elements: list[LayoutElement]
    chunks: list[DocumentChunk]


class ParsedDocument(BaseModel):
    """Intermediate result after parsing and type separation.

    The parser splits raw elements into three lanes so that each chunker
    receives only the element types it knows how to handle.
    """

    document_id: str
    filename: str
    page_count: int
    text_elements: list[LayoutElement] = Field(default_factory=list)
    table_elements: list[LayoutElement] = Field(default_factory=list)
    image_elements: list[LayoutElement] = Field(default_factory=list)
    all_elements: list[LayoutElement] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
