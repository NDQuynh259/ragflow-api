"""Docling-based PDF parser.

Docling natively separates text, tables, and pictures, making it ideal for
the type-aware chunking strategy.  OCR is enabled for scanned/bitmap PDFs.
"""

from __future__ import annotations

import uuid
from typing import Any

from rag_document_pipeline.models import (
    ImageData,
    LayoutElement,
    TableData,
)
from rag_document_pipeline.parsers.base import ParserError


def _repair_text(value: str) -> str:
    """Repair common UTF-8-as-Latin-1 mojibake without touching valid text."""
    if not value:
        return value
    markers = ("Ã", "Â", "Ä", "Å", "Æ", "Ç", "Ð", "Ñ", "â")
    if any(marker in value for marker in markers):
        try:
            repaired = value.encode("latin1").decode("utf-8")
            if repaired.count("�") <= value.count("�"):
                return repaired
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return value


class DoclingParser:
    """Parse PDFs using IBM Docling.

    Docling provides high-quality layout analysis and natively separates
    content into ``texts``, ``tables``, and ``pictures`` collections.
    This parser converts each collection into typed ``LayoutElement`` objects
    so that downstream chunkers can apply type-specific strategies.
    """

    def __init__(self, *, do_ocr: bool = True) -> None:
        self.do_ocr = do_ocr

    def parse(self, content: bytes, *, filename: str) -> list[LayoutElement]:
        if not content:
            raise ParserError("Cannot parse an empty document.")
        if not filename.lower().endswith(".pdf"):
            raise ParserError("DoclingParser supports PDF files only.")

        try:
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.document_converter import (
                DocumentConverter,
                PdfFormatOption,
            )
        except ImportError as exc:
            raise ParserError(
                "Docling is not installed. Install `docling>=2.0.0`."
            ) from exc

        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory(prefix="rag-docling-") as workdir:
            source = Path(workdir) / Path(filename).name
            source.write_bytes(content)

            pdf_options = PdfPipelineOptions(do_ocr=self.do_ocr)
            converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(
                        pipeline_options=pdf_options,
                    ),
                },
            )

            try:
                result = converter.convert(str(source))
            except Exception as exc:
                raise ParserError(
                    f"Docling failed to parse '{filename}': {exc}"
                ) from exc

        raw = result.document.export_to_dict()
        return self._to_elements(raw, filename=filename)

    # ------------------------------------------------------------------
    # Internal conversion
    # ------------------------------------------------------------------

    @classmethod
    def _to_elements(
        cls, raw: dict[str, Any], *, filename: str
    ) -> list[LayoutElement]:
        elements: list[LayoutElement] = []
        order = 0

        # --- Text elements (paragraphs, headings, lists) ---
        for idx, item in enumerate(raw.get("texts", [])):
            if item.get("content_layer") == "furniture":
                continue

            text = _repair_text(
                (item.get("orig") or item.get("text") or "").strip()
            )
            if not text:
                continue

            label = (item.get("label") or "text").lower()
            element_type = cls._map_text_type(label)
            prov = (item.get("prov") or [{}])[0]
            heading_level = cls._detect_heading_level(label, text)

            elements.append(
                LayoutElement(
                    id=item.get("self_ref", f"text-{idx}"),
                    type=element_type,
                    text=text,
                    page_number=prov.get("page_no", 1),
                    bbox=cls._extract_bbox(prov),
                    order=order,
                    heading_level=heading_level,
                    metadata={
                        "source": "docling",
                        "raw_label": label,
                        "docling_ref": item.get("self_ref"),
                    },
                )
            )
            order += 1

        # --- Table elements ---
        for idx, item in enumerate(raw.get("tables", [])):
            prov = (item.get("prov") or [{}])[0]
            table_data = cls._extract_table_data(item)
            # Build readable text from table cells
            cell_texts = []
            for row in table_data.rows:
                cell_texts.append(" | ".join(row))
            content = "\n".join(cell_texts)
            if table_data.headers:
                header_line = " | ".join(table_data.headers)
                content = f"{header_line}\n{content}"
            content = _repair_text(content)

            elements.append(
                LayoutElement(
                    id=item.get("self_ref", f"table-{idx}"),
                    type="table",
                    text=content,
                    page_number=prov.get("page_no", 1),
                    bbox=cls._extract_bbox(prov),
                    order=order,
                    table_data=table_data,
                    metadata={
                        "source": "docling",
                        "docling_ref": item.get("self_ref"),
                    },
                )
            )
            order += 1

        # --- Image/picture elements ---
        for idx, item in enumerate(raw.get("pictures", [])):
            prov = (item.get("prov") or [{}])[0]
            caption_refs = item.get("captions", [])
            caption_text = cls._resolve_captions(caption_refs, raw)

            elements.append(
                LayoutElement(
                    id=item.get("self_ref", f"image-{idx}"),
                    type="image",
                    text=caption_text or "",
                    page_number=prov.get("page_no", 1),
                    bbox=cls._extract_bbox(prov),
                    order=order,
                    image_data=ImageData(
                        caption=caption_text,
                        caption_refs=[
                            str(r) for r in caption_refs
                        ],
                    ),
                    metadata={
                        "source": "docling",
                        "docling_ref": item.get("self_ref"),
                        "child_refs": item.get("children", []),
                    },
                )
            )
            order += 1

        return elements

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _map_text_type(label: str) -> str:
        """Map Docling label to canonical element type."""
        mapping = {
            "title": "heading",
            "section_header": "heading",
            "section-header": "heading",
            "heading": "heading",
            "paragraph": "paragraph",
            "text": "text",
            "list_item": "list",
            "list-item": "list",
            "list": "list",
            "caption": "caption",
            "figure_caption": "caption",
            "page_header": "header",
            "page_footer": "footer",
            "page-header": "header",
            "page-footer": "footer",
            "formula": "formula",
        }
        return mapping.get(label, "text")

    @staticmethod
    def _detect_heading_level(label: str, text: str) -> int | None:
        """Infer heading level from label or text pattern."""
        if label in ("title", "section_header", "section-header", "heading"):
            # Simple heuristic: shorter headings are higher level
            import re

            match = re.match(r"^(\d+(?:\.\d+)*)\s", text)
            if match:
                depth = match.group(1).count(".") + 1
                return min(depth, 6)
            return 1
        return None

    @staticmethod
    def _extract_bbox(
        prov: dict[str, Any],
    ) -> tuple[float, float, float, float] | None:
        """Extract and normalize bounding box from Docling provenance."""
        bbox = prov.get("bbox")
        if not bbox:
            return None
        if isinstance(bbox, dict):
            try:
                coords = [
                    float(bbox.get("l", 0)),
                    float(bbox.get("t", 0)),
                    float(bbox.get("r", 0)),
                    float(bbox.get("b", 0)),
                ]
            except (TypeError, ValueError):
                return None
        elif isinstance(bbox, (list, tuple)) and len(bbox) == 4:
            try:
                coords = [float(v) for v in bbox]
            except (TypeError, ValueError):
                return None
        else:
            return None

        x0, y0, x1, y1 = coords
        return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))

    @staticmethod
    def _extract_table_data(item: dict[str, Any]) -> TableData:
        """Convert Docling table structure to TableData."""
        data = item.get("data") or {}
        table_cells = data.get("table_cells", [])

        if not table_cells:
            return TableData()

        # Determine grid dimensions
        max_row = 0
        max_col = 0
        for cell in table_cells:
            r = cell.get("end_row_offset_idx", cell.get("row", 0))
            c = cell.get("end_col_offset_idx", cell.get("col", 0))
            max_row = max(max_row, r)
            max_col = max(max_col, c)

        # Build grid
        grid: list[list[str]] = [
            [""] * max_col for _ in range(max_row)
        ]
        header_rows: set[int] = set()

        for cell in table_cells:
            r_start = cell.get("start_row_offset_idx", cell.get("row", 0))
            c_start = cell.get("start_col_offset_idx", cell.get("col", 0))
            r_end = cell.get("end_row_offset_idx", r_start + 1)
            c_end = cell.get("end_col_offset_idx", c_start + 1)
            text = _repair_text(cell.get("text", "")).strip()
            is_header = cell.get("column_header", False) or cell.get(
                "row_header", False
            )

            for r in range(r_start, min(r_end, max_row)):
                if is_header:
                    header_rows.add(r)
                for c in range(c_start, min(c_end, max_col)):
                    grid[r][c] = text

        headers: list[str] = []
        rows: list[list[str]] = []

        for r_idx, row in enumerate(grid):
            if r_idx in header_rows:
                if not headers:
                    headers = row
            else:
                rows.append(row)

        # If no header was detected, use first row
        if not headers and rows:
            headers = rows.pop(0)

        return TableData(
            headers=headers,
            rows=rows,
            row_start=0,
            row_end=len(rows),
        )

    @staticmethod
    def _resolve_captions(
        refs: list[Any], raw: dict[str, Any]
    ) -> str | None:
        """Resolve caption references to actual caption text."""
        if not refs:
            return None

        ref_set = {str(r) for r in refs}
        captions: list[str] = []

        for item in raw.get("texts", []):
            if item.get("self_ref") in ref_set:
                text = _repair_text(
                    (item.get("orig") or item.get("text") or "").strip()
                )
                if text:
                    captions.append(text)

        return "\n".join(captions) if captions else None
