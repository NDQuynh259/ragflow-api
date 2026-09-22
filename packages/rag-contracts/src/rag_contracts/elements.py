"""Layout element contracts shared across the workspace."""

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


class TableData(BaseModel):
    """Structured table content extracted by a parser."""

    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    row_start: int = 0
    row_end: int | None = None
    caption: str | None = None


class ImageData(BaseModel):
    """Metadata for an image/figure extracted by a parser."""

    uri: str | None = None
    caption: str | None = None
    description: str | None = None
    ocr_text: str | None = None
    caption_refs: list[str] = Field(default_factory=list)


class LayoutElement(BaseModel):
    """Core layout element — output of a parser adapter."""

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
