"""Layout-aware document parser using Unstructured.

This module implements the target "Layout Parser" component from the multimodal
RAG architecture (``docs/RAG_Architecture_Design.md`` §17). It uses the Unstructured
library to partition documents into structured layout elements:

- **Text blocks** — NarrativeText, Title, ListItem, Header, Footer, etc.
- **Table blocks** — Structured tables with Markdown rendering and row matrix extraction.
- **Image blocks** — Image regions, charts, and figure captions for vision processing.

The parser returns normalized ``LayoutBlock`` objects compatible with the ingestion
pipeline and downstream vector storage.
"""

from __future__ import annotations

import io
import unicodedata
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from typing import Any

try:
    from unstructured.partition.auto import partition
    from unstructured.partition.pdf import partition_pdf
except ImportError:  # pragma: no cover - exercised when unstructured is not installed
    partition_pdf = None
    partition = None

BLOCK_TYPE_TEXT = "text"
BLOCK_TYPE_TABLE = "table"
BLOCK_TYPE_IMAGE = "image"
BLOCK_TYPES = frozenset({BLOCK_TYPE_TEXT, BLOCK_TYPE_TABLE, BLOCK_TYPE_IMAGE})

IMAGE_CATEGORIES = frozenset({"Image", "FigureCaption", "Picture", "Graphic"})
TABLE_CATEGORIES = frozenset({"Table"})
\


class _HTMLTableExtractor(HTMLParser):
    """Parse HTML table markup into a 2D row matrix."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self.current_row: list[str] = []
        self.current_cell: list[str] = []
        self.in_cell: bool = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"td", "th"}:
            self.in_cell = True
            self.current_cell = []
        elif tag == "tr":
            self.current_row = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"}:
            self.in_cell = False
            self.current_row.append("".join(self.current_cell).strip())
        elif tag == "tr":
            if self.current_row:
                self.rows.append(self.current_row)

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            self.current_cell.append(data)


@dataclass
class LayoutBlock:
    """A single layout region extracted from a document."""

    block_type: str
    page_number: int
    bbox: tuple[float, float, float, float]  # (x0, top, x1, bottom) in points
    text: str = ""  # text content (text blocks) or Markdown (table blocks)
    rows: list[list[str | None]] | None = None  # table cells, only when block_type == "table"
    image_bytes: bytes | None = None  # reserved for downstream image extraction
    image_name: str | None = None  # object name / index, only for image blocks
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation (raw image bytes are dropped)."""
        payload = asdict(self)
        if self.image_bytes is not None:
            payload["image_size"] = len(self.image_bytes)
        payload.pop("image_bytes", None)
        payload["bbox"] = list(self.bbox)
        return payload


class LayoutParseError(ValueError):
    """Raised when a document cannot be segmented into layout blocks."""


class LayoutParser:
    """Segment documents into text, table, and image blocks using Unstructured."""

    @staticmethod
    def sanitize_text(text: str | None) -> str:
        """Normalize extracted text and remove unsafe control characters."""
        if not text:
            return ""
        normalized = unicodedata.normalize(
            "NFC", text.replace("\r\n", "\n").replace("\r", "\n")
        )
        return "".join(
            char
            for char in normalized
            if char in {"\n", "\t"}
            or unicodedata.category(char) not in {"Cc", "Cf", "Cs"}
        )

    def parse(self, file_bytes: bytes, filename: str, **kwargs: Any) -> list[LayoutBlock]:
        """Parse a document into layout blocks based on its extension."""
        extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if extension == "pdf":
            return self.parse_pdf(file_bytes, **kwargs)

        # Support other document types if unstructured partition is available
        if partition is not None:
            try:
                elements = partition(
                    file=io.BytesIO(file_bytes),
                    metadata_filename=filename,
                    **kwargs,
                )
                return self._elements_to_blocks(elements)
            except Exception as exc:
                raise LayoutParseError(f"Failed to parse document '{filename}': {exc}") from exc

        raise LayoutParseError(
            f"Layout parsing currently supports PDF files only, not: {extension or 'unknown'}."
        )

    def parse_pdf(
        self,
        file_bytes: bytes,
        strategy: str = "auto",
        infer_table_structure: bool = True,
        **kwargs: Any,
    ) -> list[LayoutBlock]:
        """Segment every page of a PDF into ordered layout blocks using Unstructured."""
        if partition_pdf is None:
            raise LayoutParseError(
                "unstructured is required for layout parsing. "
                "Install it with `pip install \"unstructured[pdf]\"`."
            )

        try:
            elements = partition_pdf(
                file=io.BytesIO(file_bytes),
                strategy=strategy,
                infer_table_structure=infer_table_structure,
                **kwargs,
            )
        except Exception as exc:
            # Fallback to fast strategy if hi_res/auto fails due to missing OCR dependencies
            if strategy not in {"fast"}:
                try:
                    elements = partition_pdf(
                        file=io.BytesIO(file_bytes),
                        strategy="fast",
                        infer_table_structure=False,
                        **kwargs,
                    )
                except Exception as fallback_exc:
                    raise LayoutParseError(f"Failed to parse PDF: {fallback_exc}") from fallback_exc
            else:
                raise LayoutParseError(f"Failed to parse PDF: {exc}") from exc

        return self._elements_to_blocks(elements)

    def _elements_to_blocks(self, elements: list[Any]) -> list[LayoutBlock]:
        """Convert a sequence of Unstructured Element objects to LayoutBlock instances."""
        blocks: list[LayoutBlock] = []

        for index, element in enumerate(elements):
            category = getattr(element, "category", "") or type(element).__name__
            text = self.sanitize_text(getattr(element, "text", "") or "")
            page_number = self._extract_page_number(element)
            bbox = self._extract_bbox(element)
            metadata = self._extract_metadata(element)

            if category in TABLE_CATEGORIES:
                html_table = getattr(getattr(element, "metadata", None), "text_as_html", None)
                rows = self._html_to_rows(html_table) if html_table else self._text_to_rows(text)
                markdown = self._rows_to_markdown(rows) if rows else text
                blocks.append(
                    LayoutBlock(
                        block_type=BLOCK_TYPE_TABLE,
                        page_number=page_number,
                        bbox=bbox,
                        text=markdown,
                        rows=rows or None,
                        metadata=metadata,
                    )
                )
            elif category in IMAGE_CATEGORIES:
                image_name = (
                    getattr(getattr(element, "metadata", None), "image_path", None)
                    or f"image-p{page_number}-{index}"
                )
                blocks.append(
                    LayoutBlock(
                        block_type=BLOCK_TYPE_IMAGE,
                        page_number=page_number,
                        bbox=bbox,
                        text=text,
                        image_name=image_name,
                        metadata=metadata,
                    )
                )
            else:
                # NarrativeText, Title, ListItem, Header, Footer, UncategorizedText, etc.
                if text.strip():
                    blocks.append(
                        LayoutBlock(
                            block_type=BLOCK_TYPE_TEXT,
                            page_number=page_number,
                            bbox=bbox,
                            text=text,
                            metadata=metadata,
                        )
                    )

        return self._sort_blocks(blocks)

    @staticmethod
    def _extract_page_number(element: Any) -> int:
        """Extract page number from element metadata (1-indexed)."""
        meta = getattr(element, "metadata", None)
        if meta is not None:
            page_number = getattr(meta, "page_number", None)
            if isinstance(page_number, int) and page_number > 0:
                return page_number
        return 1

    @staticmethod
    def _extract_bbox(element: Any) -> tuple[float, float, float, float]:
        """Extract bounding box (x0, top, x1, bottom) from element coordinates."""
        meta = getattr(element, "metadata", None)
        if meta is None:
            return (0.0, 0.0, 0.0, 0.0)

        coords = getattr(meta, "coordinates", None)
        if coords is not None:
            points = getattr(coords, "points", None)
            if points and len(points) >= 2:
                xs = [p[0] for p in points if len(p) >= 2]
                ys = [p[1] for p in points if len(p) >= 2]
                if xs and ys:
                    return (float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys)))

        # Fallback to bbox if directly present in metadata dict
        if isinstance(meta, dict) and "bbox" in meta:
            b = meta["bbox"]
            if isinstance(b, (list, tuple)) and len(b) == 4:
                return (float(b[0]), float(b[1]), float(b[2]), float(b[3]))

        return (0.0, 0.0, 0.0, 0.0)

    @staticmethod
    def _extract_metadata(element: Any) -> dict[str, Any]:
        """Extract enriched metadata from Unstructured element."""
        meta_dict: dict[str, Any] = {}
        category = getattr(element, "category", None) or type(element).__name__
        meta_dict["category"] = category

        element_id = getattr(element, "id", None)
        if element_id:
            meta_dict["element_id"] = str(element_id)

        meta = getattr(element, "metadata", None)
        if meta is not None:
            for attr in ("filename", "filetype", "parent_id", "languages"):
                val = getattr(meta, attr, None)
                if val is not None:
                    meta_dict[attr] = val
        return meta_dict

    @staticmethod
    def _html_to_rows(html_content: str) -> list[list[str]]:
        """Extract 2D row matrix from HTML table string."""
        if not html_content or "<table" not in html_content.lower():
            return []
        parser = _HTMLTableExtractor()
        try:
            parser.feed(html_content)
            return parser.rows
        except Exception:
            return []

    @staticmethod
    def _text_to_rows(text: str) -> list[list[str]]:
        """Fallback table row extraction from tab/space separated plain text."""
        if not text:
            return []
        rows: list[list[str]] = []
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            if "\t" in line:
                rows.append([cell.strip() for cell in line.split("\t")])
            elif " | " in line:
                cells = [c.strip() for c in line.strip("|").split("|")]
                rows.append(cells)
            else:
                rows.append([line])
        return rows

    @staticmethod
    def _rows_to_markdown(rows: list[list[Any]]) -> str:
        """Serialize a row matrix to a standard Markdown table string."""
        if not rows:
            return ""

        cleaned = [
            [
                "" if cell is None else str(cell).replace("|", r"\|").replace("\n", "<br>")
                for cell in row
            ]
            for row in rows
        ]
        width = max(len(row) for row in cleaned)
        if width == 0:
            return ""

        cleaned = [row + [""] * (width - len(row)) for row in cleaned]
        header = cleaned[0]
        lines = [
            "| " + " | ".join(header) + " |",
            "| " + " | ".join("---" for _ in header) + " |",
        ]
        for row in cleaned[1:]:
            lines.append("| " + " | ".join(row) + " |")
        return "\n".join(lines)

    @staticmethod
    def _sort_blocks(blocks: list[LayoutBlock]) -> list[LayoutBlock]:
        """Order blocks by reading order: page number, top coordinate, left coordinate."""
        return sorted(
            blocks,
            key=lambda b: (
                b.page_number,
                b.bbox[1],
                b.bbox[0],
            ),
        )
