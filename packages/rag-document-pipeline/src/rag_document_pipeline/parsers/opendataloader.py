from __future__ import annotations

import json
import tempfile
import uuid
from pathlib import Path
from typing import Any

from rag_document_pipeline.models import LayoutElement
from rag_document_pipeline.parsers.base import ParserError

class OpenDataLoaderParser:
    """Parse PDFs with OpenDataLoader's local Python SDK.

    OpenDataLoader requires Java 11+ and writes JSON artifacts to an output
    directory. The adapter keeps that implementation detail out of the RAG
    application and converts its schema to our stable LayoutElement contract.
    """
    def __init__(self, *, output_format: str = "json") -> None:
        if output_format != "json":
            raise ValueError("OpenDataLoaderParser requires output_format='json'")
        self.output_format = output_format

    def parse(self, content: bytes, *, filename: str) -> list[LayoutElement]:
        if not content:
            raise ParserError("Cannot parse an empty document.")
        if not filename.lower().endswith(".pdf"):
            raise ParserError("OpenDataLoaderParser supports PDF files only.")
        try:
            import opendataloader_pdf
        except ImportError as exc:
            raise ParserError(
                "OpenDataLoader is not installed. Install `opendataloader-pdf` "
                "and Java 11+ is required."
            ) from exc

        with tempfile.TemporaryDirectory(prefix="rag-opendataloader-") as workdir:
            work = Path(workdir)
            source = work / Path(filename).name
            output = work / "output"
            source.write_bytes(content)
            output.mkdir()
            try:
                opendataloader_pdf.convert(
                    input_path=[str(source)],
                    output_dir=str(output),
                    format=self.output_format,
                )
            except Exception as exc:
                raise ParserError(f"OpenDataLoader failed to parse '{filename}': {exc}") from exc
            json_file = self._find_result(output)
            if json_file is None:
                raise ParserError("OpenDataLoader completed without producing a JSON result.")
            try:
                payload = json.loads(json_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ParserError(f"Invalid OpenDataLoader JSON output: {exc}") from exc
        return self._to_elements(payload)

    @staticmethod
    def _find_result(output: Path) -> Path | None:
        candidates = sorted(output.rglob("*.json"))
        return candidates[0] if candidates else None

    @classmethod
    def _to_elements(cls, payload: Any) -> list[LayoutElement]:
        raw = payload.get("elements", payload.get("kids", payload)) if isinstance(payload, dict) else payload
        if not isinstance(raw, list):
            raise ParserError("OpenDataLoader JSON has no elements array.")
        elements: list[LayoutElement] = []
        for order, item in enumerate(raw):
            if not isinstance(item, dict):
                continue
            text = cls._text(item)
            bbox = cls._bbox(item)
            page = cls._number(item, "page_number", "page number", "page", default=1)
            element_type = str(item.get("type", item.get("element_type", "text"))).lower()
            metadata = {"source": "opendataloader", "raw_type": element_type}
            if "rows" in item:
                metadata["rows"] = item["rows"]
            if "heading level" in item:
                metadata["heading_level"] = item["heading level"]
            elements.append(LayoutElement(
                id=str(item.get("id", item.get("element_id", uuid.uuid4()))),
                type=element_type,
                text=text,
                page_number=max(1, page),
                bbox=bbox,
                source=item.get("source") if isinstance(item.get("source"), str) else None,
                caption=item.get("caption") if isinstance(item.get("caption"), str) else None,
                order=order,
                metadata=metadata,
            ))
        return elements

    @staticmethod
    def _text(item: dict[str, Any]) -> str:
        """Extract visible text from OpenDataLoader's nested JSON.

        Tables and lists commonly store their real content below ``kids`` or
        ``cells``.  Reading only the top-level ``content`` loses that text and
        produces empty elements that cannot be indexed by RAG.
        """
        parts: list[str] = []

        for key in ("content", "text", "value", "label", "title"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())

        for key in ("kids", "children", "items", "list_items"):
            children = item.get(key)
            if isinstance(children, list):
                for child in children:
                    if isinstance(child, dict):
                        child_text = OpenDataLoaderParser._text(child)
                        if child_text:
                            parts.append(child_text)

        rows = item.get("rows")
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    row_text = OpenDataLoaderParser._text(row)
                    cells = row.get("cells")
                    if isinstance(cells, list):
                        cell_text = [OpenDataLoaderParser._text(cell) for cell in cells if isinstance(cell, dict)]
                        row_text = " | ".join(part for part in cell_text if part) or row_text
                    if row_text:
                        parts.append(row_text)
                elif isinstance(row, list):
                    cells = [str(cell).strip() for cell in row if cell is not None and str(cell).strip()]
                    if cells:
                        parts.append(" | ".join(cells))

        # Preserve order while removing duplicates caused by parent/child
        # objects repeating the same visible text.
        return "\n".join(dict.fromkeys(parts))

    @staticmethod
    def _number(item: dict[str, Any], *keys: str, default: int = 1) -> int:
        for key in keys:
            if key in item:
                try: return int(item[key])
                except (TypeError, ValueError): pass
        return default

    @staticmethod
    def _bbox(item: dict[str, Any]) -> tuple[float, float, float, float] | None:
        value = item.get("bounding box", item.get("bbox", item.get("bounding_box")))
        if isinstance(value, str):
            try:
                value = [float(part) for part in value.replace(",", " ").split()]
            except ValueError:
                value = None
        if isinstance(value, dict):
            value = [value.get(k) for k in ("left", "bottom", "right", "top")]
        if not isinstance(value, (list, tuple)) or len(value) != 4:
            return None
        try:
            x0, y0, x1, y1 = (float(v) for v in value)
            return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
        except (TypeError, ValueError): return None
