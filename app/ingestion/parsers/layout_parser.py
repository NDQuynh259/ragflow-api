"""Layout-aware PDF parser: partition a page into text, table, and image blocks.

This module implements the target "Layout Parser" component from the multimodal
RAG architecture (``docs/RAG_Architecture_Design.md`` §17). It uses pdfplumber for
geometry-based segmentation:

- **Text blocks** — words are clustered into lines (by ``top`` coordinate), then
  lines are clustered into paragraphs by vertical gap.
- **Table blocks** — detected with ``page.find_tables()`` and serialized to both a
  row matrix and a Markdown string.
- **Image blocks** — detected from the page image catalog (bounding box + name).

The parser is side-effect free and returns plain data objects so it can be tested
independently and wired into the async ingestion worker later. Raw image byte
extraction is intentionally left to a dedicated ``ImageExtractor`` (downstream of
the "Image → Classify → Vision" stage); this parser only *locates and labels*
image regions.
"""

from __future__ import annotations

import io
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any

try:
    import pdfplumber
except ImportError:  # pragma: no cover - exercised only when the dependency is absent
    pdfplumber = None

BLOCK_TYPE_TEXT = "text"
BLOCK_TYPE_TABLE = "table"
BLOCK_TYPE_IMAGE = "image"
BLOCK_TYPES = frozenset({BLOCK_TYPE_TEXT, BLOCK_TYPE_TABLE, BLOCK_TYPE_IMAGE})


@dataclass
class LayoutBlock:
    """A single layout region extracted from a page."""

    block_type: str
    page_number: int
    bbox: tuple[float, float, float, float]  # (x0, top, x1, bottom) in PDF points
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
    """Segment PDF pages into text, table, and image blocks."""

    LINE_TOLERANCE = 3.0  # points: max vertical drift for words on the same line
    PARAGRAPH_GAP_FACTOR = 1.5  # gap (in line-heights) that starts a new text block
    COLUMN_GUTTER_MIN = 24.0  # points: min horizontal gap treated as a column gutter
    COLUMN_GUTTER_FACTOR = 3.0  # gutter must exceed this multiple of the median word gap

    @staticmethod
    def sanitize_text(text: str | None) -> str:
        """Normalize extracted PDF text and remove unsafe control characters."""
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

    def parse(self, file_bytes: bytes, filename: str) -> list[LayoutBlock]:
        """Parse a file into layout blocks, dispatching on its extension."""
        extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if extension == "pdf":
            return self.parse_pdf(file_bytes)

        raise LayoutParseError(
            f"Layout parsing currently supports PDF files only, not: {extension or 'unknown'}."
        )

    def parse_pdf(self, file_bytes: bytes) -> list[LayoutBlock]:
        """Segment every page of a PDF into ordered layout blocks."""
        if pdfplumber is None:
            raise LayoutParseError(
                "pdfplumber is required for layout parsing. "
                "Install it with `pip install pdfplumber`."
            )

        blocks: list[LayoutBlock] = []
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                blocks.extend(self._parse_page(page, page_number))
        return self._sort_blocks(blocks)

    def _parse_page(self, page: Any, page_number: int) -> list[LayoutBlock]:
        table_blocks = self._extract_table_blocks(page, page_number)
        blocks: list[LayoutBlock] = []
        blocks.extend(self._extract_text_blocks(page, page_number, table_blocks))
        blocks.extend(table_blocks)
        blocks.extend(self._extract_image_blocks(page, page_number))
        return blocks

    # ------------------------------------------------------------------ text ----
    def _extract_text_blocks(
        self,
        page: Any,
        page_number: int,
        table_blocks: list[LayoutBlock] | None = None,
    ) -> list[LayoutBlock]:
        words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
        table_bboxes = [block.bbox for block in table_blocks or []]
        words = [
            word
            for word in words
            if not any(self._word_is_in_bbox(word, bbox) for bbox in table_bboxes)
        ]
        if not words:
            return []

        boundaries = self._detect_column_boundaries(self._words_to_lines(words))
        columns = self._split_words_into_columns(words, boundaries)
        multi_column = len(columns) > 1

        result: list[LayoutBlock] = []
        for column_index, column_words in enumerate(columns):
            for block in self._lines_to_blocks(self._words_to_lines(column_words)):
                text_lines = [
                    " ".join(
                        word["text"]
                        for word in sorted(line["words"], key=lambda w: w["x0"])
                    )
                    for line in block["lines"]
                ]
                metadata = (
                    {"column_index": column_index, "column_count": len(columns)}
                    if multi_column
                    else {}
                )
                result.append(
                    LayoutBlock(
                        block_type=BLOCK_TYPE_TEXT,
                        page_number=page_number,
                        bbox=(block["x0"], block["top"], block["x1"], block["bottom"]),
                        text="\n".join(text_lines),
                        metadata=metadata,
                    )
                )
        return result

    @staticmethod
    def _word_is_in_bbox(
        word: dict[str, Any], bbox: tuple[float, float, float, float]
    ) -> bool:
        """Return whether the word center is inside a table bounding box."""
        x0, top, x1, bottom = bbox
        center_x = (word["x0"] + word["x1"]) / 2.0
        center_y = (word["top"] + word["bottom"]) / 2.0
        return x0 <= center_x <= x1 and top <= center_y <= bottom

    @classmethod
    def _words_to_lines(cls, words: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Cluster words that share a baseline into lines."""
        lines: list[dict[str, Any]] = []
        for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
            if lines and abs(word["top"] - lines[-1]["top"]) <= cls.LINE_TOLERANCE:
                line = lines[-1]
                line["words"].append(word)
                line["top"] = min(line["top"], word["top"])
                line["bottom"] = max(line["bottom"], word["bottom"])
                line["x0"] = min(line["x0"], word["x0"])
                line["x1"] = max(line["x1"], word["x1"])
            else:
                lines.append(
                    {
                        "top": word["top"],
                        "bottom": word["bottom"],
                        "x0": word["x0"],
                        "x1": word["x1"],
                        "words": [word],
                    }
                )
        return lines

    @classmethod
    def _lines_to_blocks(cls, lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Cluster lines into paragraphs by vertical gap relative to line height."""
        if not lines:
            return []

        heights = sorted(line["bottom"] - line["top"] for line in lines)
        line_height = heights[len(heights) // 2] or 1.0
        gap_threshold = line_height * cls.PARAGRAPH_GAP_FACTOR

        blocks: list[dict[str, Any]] = []
        for line in lines:
            if blocks and (line["top"] - blocks[-1]["bottom"]) <= gap_threshold:
                block = blocks[-1]
                block["lines"].append(line)
                block["bottom"] = max(block["bottom"], line["bottom"])
                block["x0"] = min(block["x0"], line["x0"])
                block["x1"] = max(block["x1"], line["x1"])
            else:
                blocks.append(
                    {
                        "top": line["top"],
                        "bottom": line["bottom"],
                        "x0": line["x0"],
                        "x1": line["x1"],
                        "lines": [line],
                    }
                )
        return blocks

    @classmethod
    def _detect_column_boundaries(cls, lines: list[dict[str, Any]]) -> list[float]:
        """Return x-positions that separate columns, from within-line horizontal gaps."""
        within_line_gaps: list[float] = []
        for line in lines:
            words = sorted(line["words"], key=lambda w: w["x0"])
            for left, right in zip(words, words[1:]):
                gap = right["x0"] - left["x1"]
                if gap > 0:
                    within_line_gaps.append(gap)
        if not within_line_gaps:
            return []

        ordered = sorted(within_line_gaps)
        median_gap = ordered[len(ordered) // 2]
        threshold = max(cls.COLUMN_GUTTER_MIN, median_gap * cls.COLUMN_GUTTER_FACTOR)

        boundaries: set[float] = set()
        for line in lines:
            words = sorted(line["words"], key=lambda w: w["x0"])
            for left, right in zip(words, words[1:]):
                gap = right["x0"] - left["x1"]
                if gap >= threshold:
                    boundaries.add(round((left["x1"] + right["x0"]) / 2.0, 1))
        return sorted(boundaries)

    @classmethod
    def _split_words_into_columns(
        cls, words: list[dict[str, Any]], boundaries: list[float]
    ) -> list[list[dict[str, Any]]]:
        """Bucket words into columns according to the detected gutter positions."""
        if not boundaries:
            return [words]
        columns: list[list[dict[str, Any]]] = [[] for _
         in range(len(boundaries) + 1)]
        for word in words:
            center = (word["x0"] + word["x1"]) / 2.0
            index = sum(1 for boundary in boundaries if boundary < center)
            columns[index].append(word)
        return [column for column in columns if column]

    # ----------------------------------------------------------------- table ----
    def _extract_table_blocks(self, page: Any, page_number: int) -> list[LayoutBlock]:
        result: list[LayoutBlock] = []
        for table in page.find_tables():
            rows = table.extract() or []
            result.append(
                LayoutBlock(
                    block_type=BLOCK_TYPE_TABLE,
                    page_number=page_number,
                    bbox=tuple(table.bbox),
                    text=self._rows_to_markdown(rows),
                    rows=rows,
                )
            )
        return result

    @staticmethod
    def _rows_to_markdown(rows: list[list[Any]]) -> str:
        """Serialize a row matrix to a Markdown table string."""
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
        cleaned = [row + [""] * (width - len(row)) for row in cleaned]

        header = cleaned[0]
        lines = [
            "| " + " | ".join(header) + " |",
            "| " + " | ".join("---" for _ in header) + " |",
        ]
        for row in cleaned[1:]:
            lines.append("| " + " | ".join(row) + " |")
        return "\n".join(lines)

    # ----------------------------------------------------------------- image ----
    def _extract_image_blocks(self, page: Any, page_number: int) -> list[LayoutBlock]:
        result: list[LayoutBlock] = []
        images = getattr(page, "images", None) or []
        for index, image in enumerate(images):
            bbox = (
                image.get("x0", 0.0),
                image.get("top", 0.0),
                image.get("x1", 0.0),
                image.get("bottom", 0.0),
            )
            result.append(
                LayoutBlock(
                    block_type=BLOCK_TYPE_IMAGE,
                    page_number=page_number,
                    bbox=bbox,
                    image_name=image.get("name") or f"image-{page_number}-{index}",
                    metadata={
                        "width": image.get("width"),
                        "height": image.get("height"),
                    },
                )
            )
        return result

    # ---------------------------------------------------------------- ordering ----
    @staticmethod
    def _sort_blocks(blocks: list[LayoutBlock]) -> list[LayoutBlock]:
        """Order blocks by reading order: page, column, then top, then left."""
        return sorted(
            blocks,
            key=lambda b: (
                b.page_number,
                b.metadata.get("column_index", 0),
                b.bbox[1],
                b.bbox[0],
            ),
        )
