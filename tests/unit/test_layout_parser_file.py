"""Opt-in integration test for inspecting layouts extracted from a real file.

Run with::

    pytest -s tests/unit/test_layout_parser_file.py --layout-file path/to/file.pdf

The test is skipped when no input is supplied, so the regular test suite does
not depend on a local document or on optional OCR/model dependencies.
"""

import json

import pytest

from app.ingestion.parsers.layout_parser import LayoutParser


def test_parse_file_and_print_layouts(layout_file):
    """Parse a user-provided document and print every normalized layout block."""
    if layout_file is None:
        pytest.skip("Pass --layout-file path/to/document.pdf to inspect parsed layouts")

    if not layout_file.is_file():
        pytest.fail(f"Input file does not exist: {layout_file}")

    blocks = LayoutParser().parse(
        layout_file.read_bytes(),
        layout_file.name,
    )

    # JSON makes page, bounding box, category, table rows, and text easy to
    # inspect while omitting binary image payloads via LayoutBlock.to_dict().
    print(json.dumps([block.to_dict() for block in blocks], ensure_ascii=False, indent=2))
    assert isinstance(blocks, list)
    assert all(block.block_type in {"text", "table", "image"} for block in blocks)
