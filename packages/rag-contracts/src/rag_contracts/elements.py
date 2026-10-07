"""Layout element contracts shared across the workspace."""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger(__name__)


class ElementType(str, Enum):
    """Canonical element types produced by document parsers."""

    TEXT = "text"
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST = "list"
    TABLE = "table"
    DATA_TABLE = "data_table"
    IMAGE = "image"
    FIGURE = "figure"
    CAPTION = "caption"
    FOOTNOTE = "footnote"
    FORMULA = "formula"
    HEADER = "header"
    FOOTER = "footer"


class TableData(BaseModel):
    """Structured table content extracted by a parser."""

    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    row_start: int = Field(default=0, ge=0)
    row_end: int | None = Field(default=None, ge=0)
    caption: str | None = None

    @model_validator(mode="after")
    def _validate_row_bounds(self) -> TableData:
        if self.row_end is not None and self.row_end < self.row_start:
            raise ValueError("row_end must be greater than or equal to row_start")
        return self


class ImageData(BaseModel):
    """Metadata for an image/figure extracted by a parser."""

    uri: str | None = None
    caption: str | None = None
    description: str | None = None
    ocr_text: str | None = None
    caption_refs: list[str] = Field(default_factory=list)


class LayoutElement(BaseModel):
    """Core layout element — output of a parser adapter.

    Parsers may emit element types outside :class:`ElementType`; such values are
    coerced to ``ElementType.TEXT`` with a warning so downstream routing keeps
    working. The original parser value must be preserved by the adapter in
    ``metadata["raw_type"]``.
    """

    id: str
    type: ElementType
    text: str = ""
    page_number: int = Field(default=1, ge=1)
    bbox: tuple[float, float, float, float] | None = None
    source: str | None = None
    caption: str | None = None
    order: int = Field(default=0, ge=0)
    heading_level: int | None = Field(default=None, ge=1, le=6)
    section_path: list[str] = Field(default_factory=list)
    table_data: TableData | None = None
    image_data: ImageData | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("type", mode="before")
    @classmethod
    def _coerce_element_type(cls, value: Any) -> Any:
        if isinstance(value, ElementType):
            return value
        if not isinstance(value, str):
            return value
        normalized = value.strip().lower()
        try:
            return ElementType(normalized)
        except ValueError:
            logger.warning(
                "Unknown element type %r coerced to %r; preserve the raw value in metadata",
                value,
                ElementType.TEXT.value,
            )
            return ElementType.TEXT


__all__ = ["ElementType", "ImageData", "LayoutElement", "TableData"]
