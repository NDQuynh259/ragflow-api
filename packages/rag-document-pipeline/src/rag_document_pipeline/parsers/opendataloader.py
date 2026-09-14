from __future__ import annotations

import json
import tempfile
import uuid
from pathlib import Path
from typing import Any

from rag_document_pipeline.models import ImageData, LayoutElement, TableData
from rag_document_pipeline.parsers.base import ParserError

class OpenDataLoaderParser:
    """Parse PDFs with OpenDataLoader's local Python SDK.

    OpenDataLoader requires Java 11+ and writes JSON artifacts to an output
    directory. The adapter keeps that implementation detail out of the RAG
    application and converts its schema to our stable LayoutElement contract.
    """
    def __init__(
        self,
        *,
        output_format: str = "json",
        image_output: str = "external",
        image_dir: str | Path | None = None,
    ) -> None:
        if output_format != "json":
            raise ValueError("OpenDataLoaderParser requires output_format='json'")
        self.output_format = output_format
        self.image_output = image_output
        self.image_dir = Path(image_dir) if image_dir else None

    def parse(
        self,
        content: bytes,
        *,
        filename: str,
        image_dir: str | Path | None = None,
    ) -> list[LayoutElement]:
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

        target_image_dir = Path(image_dir) if image_dir else self.image_dir
        if target_image_dir:
            target_image_dir.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="rag-opendataloader-") as workdir:
            work = Path(workdir)
            source = work / Path(filename).name
            output = work / "output"
            source.write_bytes(content)
            output.mkdir()
            try:
                convert_kwargs: dict[str, Any] = {
                    "input_path": [str(source)],
                    "output_dir": str(output),
                    "format": self.output_format,
                    "image_output": self.image_output,
                }
                if target_image_dir:
                    convert_kwargs["image_dir"] = str(target_image_dir.resolve())
                opendataloader_pdf.convert(**convert_kwargs)
            except Exception as exc:
                raise ParserError(f"OpenDataLoader failed to parse '{filename}': {exc}") from exc
            json_file = self._find_result(output)
            if json_file is None:
                raise ParserError("OpenDataLoader completed without producing a JSON result.")
            try:
                payload = json.loads(json_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ParserError(f"Invalid OpenDataLoader JSON output: {exc}") from exc
        return self._to_elements(payload, image_dir=target_image_dir)

    @staticmethod
    def _find_result(output: Path) -> Path | None:
        candidates = sorted(output.rglob("*.json"))
        return candidates[0] if candidates else None


    # region _to_elements
    
    @classmethod
    def _to_elements(cls, payload: Any, *, image_dir: Path | None = None) -> list[LayoutElement]:
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

            image_data: ImageData | None = None
            if element_type in ("image", "figure"):
                uri = item.get("data")
                if not uri:
                    raw_source = item.get("source")
                    if raw_source:
                        if image_dir:
                            img_name = Path(raw_source).name
                            img_path = image_dir / img_name
                            try:
                                uri = str(img_path.resolve().relative_to(Path.cwd().resolve()).as_posix())
                            except ValueError:
                                uri = str(img_path.as_posix())
                        else:
                            uri = raw_source
                caption = item.get("caption") if isinstance(item.get("caption"), str) else None
                image_data = ImageData(
                    uri=uri,
                    caption=caption,
                )

            table_data: TableData | None = None
            if element_type in ("table", "data_table") and "rows" in item:
                table_data = cls._extract_table_data(item["rows"], caption=item.get("caption"))

            elements.append(LayoutElement(
                id=str(item.get("id", item.get("element_id", uuid.uuid4()))),
                type=element_type,
                text=text,
                page_number=max(1, page),
                bbox=bbox,
                source=item.get("source") if isinstance(item.get("source"), str) else None,
                caption=item.get("caption") if isinstance(item.get("caption"), str) else None,
                order=order,
                heading_level=item.get("heading level") if isinstance(item.get("heading level"), int) else None,
                table_data=table_data,
                image_data=image_data,
                metadata=metadata,
            ))
        return elements

    @classmethod
    def _extract_table_data(cls, rows: list[Any], caption: str | None = None) -> TableData | None:
        if not rows:
            return None
        parsed_rows: list[list[str]] = []
        for r in rows:
            if isinstance(r, dict):
                cells = r.get("cells")
                if isinstance(cells, list):
                    cell_texts = []
                    for c in cells:
                        if isinstance(c, dict):
                            cell_texts.append(cls._text(c))
                        else:
                            cell_texts.append(str(c) if c is not None else "")
                    parsed_rows.append(cell_texts)
            elif isinstance(r, list):
                parsed_rows.append([str(c) if c is not None else "" for c in r])
        if not parsed_rows:
            return None
        headers = parsed_rows[0]
        data_rows = parsed_rows[1:] if len(parsed_rows) > 1 else []
        return TableData(
            headers=headers,
            rows=data_rows,
            caption=caption,
        )

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

        for key in ("kids", "children", "items", "list_items", "list items"):
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
