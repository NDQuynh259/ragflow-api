"""Pure mapping helpers: OpenDataLoader JSON → LayoutElement contract.

Keeping these helpers module-level (instead of ``@staticmethod`` members of the
parser) lets the adapter stay focused on invoking the SDK and reading JSON,
while the schema translation remains independently testable.
"""

from __future__ import annotations

import logging
import math
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from urllib.request import url2pathname

from rag_contracts import ElementType
from rag_document_pipeline.models import ImageData, LayoutElement, TableData

logger = logging.getLogger(__name__)

TEXT_KEYS = ("content", "text", "value", "label", "title")
CHILD_KEYS = ("kids", "children", "items", "list_items", "list items")
IMAGE_TYPES = ("image", "figure")
TABLE_TYPES = ("table", "data_table")
BBOX_KEYS = ("bounding box", "bbox", "bounding_box")
PAGE_KEYS = ("page_number", "page number", "page")


# region elements_from_payload
def elements_from_payload(payload: Any, *, image_dir: Path | None = None) -> list[LayoutElement]:
    """Convert a decoded OpenDataLoader payload into stable layout elements."""
    raw = (
        payload.get("elements", payload.get("kids", payload))
        if isinstance(payload, dict)
        else payload
    )
    if not isinstance(raw, list):
        raise ValueError("OpenDataLoader JSON has no elements array.")

    known_types = {member.value for member in ElementType}
    elements: list[LayoutElement] = []

    for order, item in enumerate(raw):
        if not isinstance(item, dict):
            continue

        element_type = str(item.get("type", item.get("element_type", "text"))).lower()
        metadata: dict[str, Any] = {"source": "opendataloader", "raw_type": element_type}
        if "rows" in item:
            metadata["rows"] = item["rows"]
        if "heading level" in item:
            metadata["heading_level"] = item["heading level"]

        image_data: ImageData | None = None
        if element_type in IMAGE_TYPES:
            image_data = image_data_from_item(item, image_dir=image_dir, metadata=metadata)

        table_data: TableData | None = None
        if element_type in TABLE_TYPES and "rows" in item:
            table_data = table_data_from_rows(item["rows"], caption=item.get("caption"))

        elements.append(
            LayoutElement(
                id=str(item.get("id", item.get("element_id", uuid.uuid4()))),
                type=ElementType(element_type) if element_type in known_types else ElementType.TEXT,
                text=extract_visible_text(item),
                page_number=max(1, parse_positive_int(item, *PAGE_KEYS, default=1)),
                bbox=parse_bbox(item),
                source=item.get("source") if isinstance(item.get("source"), str) else None,
                caption=item.get("caption") if isinstance(item.get("caption"), str) else None,
                order=order,
                heading_level=parse_heading_level(item),
                table_data=table_data,
                image_data=image_data,
                metadata=metadata,
            )
        )

    return elements


# endregion


# region image_data_from_item
def image_data_from_item(
    item: dict[str, Any],
    *,
    image_dir: Path | None,
    metadata: dict[str, Any],
) -> ImageData:
    """Build ImageData and record intrinsic dimensions for downstream triage."""
    uri = item.get("data")
    raw_source = item.get("source")
    if not uri and isinstance(raw_source, str) and raw_source:
        if image_dir:
            img_path = image_dir / Path(raw_source).name
            try:
                uri = str(img_path.resolve().relative_to(Path.cwd().resolve()).as_posix())
            except ValueError:
                uri = img_path.as_posix()
        else:
            uri = raw_source

    caption = item.get("caption") if isinstance(item.get("caption"), str) else None
    dimensions = image_dimensions(uri)
    if dimensions is not None:
        metadata["width"], metadata["height"] = dimensions

    return ImageData(uri=uri, caption=caption)


# endregion


# region image_dimensions
def image_dimensions(uri: str | None) -> tuple[int, int] | None:
    """Return intrinsic ``(width, height)`` for a local image file.

    Returns ``None`` for remote URIs, unreadable files, or a missing Pillow
    installation — the image chunker then falls back to the layout bbox.
    """
    if not uri:
        return None

    # Only an explicit ``scheme://`` marks a remote location. Windows drive
    # paths (``C:\\x.png``) also contain a colon, so a bare urlsplit would
    # misread them as remote URIs and skip the dimension probe.
    if "://" in uri:
        parsed = urlsplit(uri)
        if parsed.scheme.lower() != "file":
            return None
        # ``file:///C:/x.png`` -> path ``/C:/x.png``; url2pathname strips the
        # leading slash so Windows recognizes the drive letter.
        raw_path = url2pathname(parsed.path)
    else:
        raw_path = uri

    path = Path(raw_path)
    if not path.is_file():
        return None

    try:
        from PIL import Image  # type: ignore[import-untyped]
    except ImportError:
        logger.debug("Pillow not available; skipping image dimension probe for %s", uri)
        return None

    try:
        with Image.open(path) as img:
            width, height = img.size
    except Exception as exc:  # noqa: BLE001 - dimension probe must never fail parsing
        logger.debug("Could not read image dimensions for %s: %s", uri, exc)
        return None

    return (int(width), int(height)) if width and height else None


# endregion


# region table_data_from_rows
def table_data_from_rows(rows: Any, caption: str | None = None) -> TableData | None:
    """Convert nested OpenDataLoader rows into header/data ``TableData``."""
    if not isinstance(rows, list) or not rows:
        return None

    parsed_rows: list[list[str]] = []
    for row in rows:
        if isinstance(row, dict):
            cells = row.get("cells")
            if isinstance(cells, list):
                parsed_rows.append(
                    [
                        extract_visible_text(cell)
                        if isinstance(cell, dict)
                        else (str(cell) if cell is not None else "")
                        for cell in cells
                    ]
                )
        elif isinstance(row, list):
            parsed_rows.append([str(cell) if cell is not None else "" for cell in row])

    if not parsed_rows:
        return None

    return TableData(headers=parsed_rows[0], rows=parsed_rows[1:], caption=caption)


# endregion


# region extract_visible_text
def extract_visible_text(item: dict[str, Any]) -> str:
    """Extract visible text from OpenDataLoader's nested JSON.

    Tables and lists commonly store their real content below ``kids`` or
    ``cells``. Reading only the top-level ``content`` loses that text and
    produces empty elements that cannot be indexed by RAG.
    """
    parts: list[str] = []

    for key in TEXT_KEYS:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())

    for key in CHILD_KEYS:
        children = item.get(key)
        if isinstance(children, list):
            parts.extend(
                child_text
                for child in children
                if isinstance(child, dict)
                for child_text in [extract_visible_text(child)]
                if child_text
            )

    rows = item.get("rows")
    if isinstance(rows, list):
        parts.extend(_row_texts(rows))

    # Preserve order while removing duplicates caused by parent/child
    # objects repeating the same visible text.
    return "\n".join(dict.fromkeys(parts))


def _row_texts(rows: list[Any]) -> list[str]:
    """Collect readable text from dict or list rows, joining cells with ``|``."""
    texts: list[str] = []
    for row in rows:
        if isinstance(row, dict):
            row_text = extract_visible_text(row)
            cells = row.get("cells")
            if isinstance(cells, list):
                cell_text = [extract_visible_text(c) for c in cells if isinstance(c, dict)]
                row_text = " | ".join(part for part in cell_text if part) or row_text
            if row_text:
                texts.append(row_text)
        elif isinstance(row, list):
            cells = [str(cell).strip() for cell in row if cell is not None and str(cell).strip()]
            if cells:
                texts.append(" | ".join(cells))
    return texts


# endregion


# region parse_bbox
def parse_bbox(item: dict[str, Any]) -> tuple[float, float, float, float] | None:
    """Normalize the many bbox shapes OpenDataLoader emits into ``(l,b,r,t)``."""
    value = next((item[key] for key in BBOX_KEYS if key in item), None)

    if isinstance(value, str):
        value = _split_numeric_string(value)
    if isinstance(value, dict):
        value = [value.get(k) for k in ("left", "bottom", "right", "top")]
    if not isinstance(value, (list, tuple)):
        return None

    coords = _to_floats(value)
    if coords is None or len(coords) != 4:
        return None
    x0, y0, x1, y1 = coords

    left, right = min(x0, x1), max(x0, x1)
    bottom, top = min(y0, y1), max(y0, y1)
    if right <= left or top <= bottom:
        return None
    return (left, bottom, right, top)


def _split_numeric_string(value: str) -> list[float] | None:
    """Parse a ``"l b r t"`` bbox string; ``None`` when it is not numeric."""
    try:
        return [float(part) for part in value.replace(",", " ").split()]
    except ValueError:
        return None


def _to_floats(values: Any) -> list[float] | None:
    """Convert bbox entries to finite floats, rejecting holes and junk."""
    coords: list[float] = []
    for entry in values:
        if entry is None:
            return None
        try:
            coord = float(entry)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(coord):
            return None
        coords.append(coord)
    return coords


# endregion


# region heading level / page number
def parse_heading_level(item: dict[str, Any]) -> int | None:
    """Return a validated heading level in the supported 1-6 range."""
    value = item.get("heading level")
    if not isinstance(value, int) or isinstance(value, bool):
        return None
    return value if 1 <= value <= 6 else None


def parse_positive_int(
    item: dict[str, Any],
    *keys: str,
    default: int = 1,
) -> int:
    """Read the first key holding a positive integer, falling back to ``default``."""
    for key in keys:
        if key not in item:
            continue
        try:
            value = int(item[key])
        except (TypeError, ValueError):
            logger.warning("Invalid numeric parser field %r in item; using default", key)
            continue
        if value >= 1:
            return value
    return default


# endregion


__all__ = [
    "elements_from_payload",
    "extract_visible_text",
    "image_data_from_item",
    "image_dimensions",
    "parse_bbox",
    "parse_heading_level",
    "parse_positive_int",
    "table_data_from_rows",
]
