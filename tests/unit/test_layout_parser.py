"""Unit tests for the LayoutParser (multimodal layout segmentation)."""

from types import SimpleNamespace

import pytest

from app.ingestion.parsers.layout import (
    BLOCK_TYPE_IMAGE,
    BLOCK_TYPE_TABLE,
    BLOCK_TYPE_TEXT,
    LayoutBlock,
    LayoutParseError,
    LayoutParser,
)


# --------------------------------------------------------------------------- #
# Minimal PDF fixture builder (valid xref, single page, Helvetica text).
# --------------------------------------------------------------------------- #
def _build_minimal_pdf(lines):
    """Build a valid single-page PDF with text at explicit coordinates.

    ``lines`` is a list of ``(x, y, text)`` tuples in PDF user space (bottom-left
    origin). Text must not contain parentheses or backslashes.
    """
    content_parts = ["BT /F1 12 Tf"]
    for x, y, text in lines:
        content_parts.append(f"1 0 0 1 {x} {y} Tm ({text}) Tj")
    content_parts.append("ET")
    content_stream = " ".join(content_parts)

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        (
            b"<< /Length " + str(len(content_stream)).encode() + b" >>\n"
            b"stream\n" + content_stream.encode() + b"\nendstream"
        ),
    ]

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += f"{index} 0 obj\n".encode()
        pdf += obj + b"\nendobj\n"

    xref_offset = len(pdf)
    count = len(objects) + 1
    pdf += f"xref\n0 {count}\n".encode()
    pdf += b"0000000000 65535 f \n"
    for offset in offsets:
        pdf += f"{offset:010d} 00000 n \n".encode()
    pdf += (
        f"trailer\n<< /Size {count} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    ).encode()
    return bytes(pdf)


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
def test_parse_pdf_extracts_text_block():
    parser = LayoutParser()
    pdf = _build_minimal_pdf([(72, 720, "Hello World")])

    blocks = parser.parse_pdf(pdf)

    text_blocks = [b for b in blocks if b.block_type == BLOCK_TYPE_TEXT]
    assert text_blocks, "expected at least one text block"
    assert "Hello World" in text_blocks[0].text


def test_parse_pdf_sorts_blocks_by_reading_order():
    parser = LayoutParser()
    pdf = _build_minimal_pdf(
        [
            (72, 720, "Top line"),
            (72, 700, "Bottom line"),
        ]
    )

    blocks = parser.parse_pdf(pdf)

    text_blocks = [b for b in blocks if b.block_type == BLOCK_TYPE_TEXT]
    assert len(text_blocks) >= 1
    tops = [b.bbox[1] for b in text_blocks]
    assert tops == sorted(tops)


def test_parse_non_pdf_falls_back_to_single_text_block():
    parser = LayoutParser()

    blocks = parser.parse(b"plain text content", "note.txt")

    assert len(blocks) == 1
    assert blocks[0].block_type == BLOCK_TYPE_TEXT
    assert blocks[0].text == "plain text content"
    assert blocks[0].page_number == 1


def test_parse_pdf_raises_when_pdfplumber_missing(monkeypatch):
    import app.ingestion.parsers.layout as layout_module

    monkeypatch.setattr(layout_module, "pdfplumber", None)

    with pytest.raises(LayoutParseError, match="pdfplumber"):
        LayoutParser().parse_pdf(b"%PDF-1.4")


def test_words_to_lines_groups_same_baseline():
    words = [
        {"top": 100.0, "bottom": 112.0, "x0": 10.0, "x1": 30.0, "text": "Hello"},
        {"top": 101.5, "bottom": 113.5, "x0": 35.0, "x1": 55.0, "text": "World"},
        {"top": 130.0, "bottom": 142.0, "x0": 10.0, "x1": 40.0, "text": "Next"},
    ]

    lines = LayoutParser._words_to_lines(words)

    assert len(lines) == 2
    assert [w["text"] for w in lines[0]["words"]] == ["Hello", "World"]
    assert [w["text"] for w in lines[1]["words"]] == ["Next"]


def test_lines_to_blocks_splits_on_large_vertical_gap():
    lines = [
        {"top": 100.0, "bottom": 112.0, "x0": 10.0, "x1": 50.0, "words": []},
        {"top": 114.0, "bottom": 126.0, "x0": 10.0, "x1": 50.0, "words": []},
        {"top": 300.0, "bottom": 312.0, "x0": 10.0, "x1": 50.0, "words": []},
    ]

    blocks = LayoutParser._lines_to_blocks(lines)

    assert len(blocks) == 2
    assert len(blocks[0]["lines"]) == 2
    assert len(blocks[1]["lines"]) == 1


def test_rows_to_markdown_builds_table():
    rows = [["Name", "Age"], ["Alice", "30"], [None, "40"]]

    markdown = LayoutParser._rows_to_markdown(rows)

    assert "| Name | Age |" in markdown
    assert "| --- | --- |" in markdown
    assert "| Alice | 30 |" in markdown
    assert "|  | 40 |" in markdown


def test_rows_to_markdown_empty_returns_empty_string():
    assert LayoutParser._rows_to_markdown([]) == ""


def test_extract_image_blocks_reads_page_image_catalog():
    page = SimpleNamespace(
        images=[
            {
                "x0": 10.0,
                "top": 20.0,
                "x1": 110.0,
                "bottom": 120.0,
                "name": "Im0",
                "width": 100,
                "height": 100,
            }
        ]
    )

    blocks = LayoutParser()._extract_image_blocks(page, page_number=1)

    assert len(blocks) == 1
    assert blocks[0].block_type == BLOCK_TYPE_IMAGE
    assert blocks[0].image_name == "Im0"
    assert blocks[0].bbox == (10.0, 20.0, 110.0, 120.0)


def test_extract_image_blocks_handles_missing_catalog():
    page = SimpleNamespace()

    blocks = LayoutParser()._extract_image_blocks(page, page_number=1)

    assert blocks == []


def test_layout_block_to_dict_drops_image_bytes():
    block = LayoutBlock(
        block_type=BLOCK_TYPE_IMAGE,
        page_number=2,
        bbox=(1.0, 2.0, 3.0, 4.0),
        image_bytes=b"\x89PNG",
        image_name="Im0",
    )

    payload = block.to_dict()

    assert "image_bytes" not in payload
    assert payload["image_size"] == 4
    assert payload["bbox"] == [1.0, 2.0, 3.0, 4.0]
    assert payload["page_number"] == 2


def test_detect_column_boundaries_detects_wide_gutter():
    lines = [
        {
            "words": [
                {"x0": 10.0, "x1": 30.0},
                {"x0": 33.0, "x1": 53.0},
                {"x0": 300.0, "x1": 320.0},
                {"x0": 323.0, "x1": 343.0},
            ]
        }
    ]

    boundaries = LayoutParser._detect_column_boundaries(lines)

    assert len(boundaries) == 1
    assert 53.0 < boundaries[0] < 300.0


def test_detect_column_boundaries_ignores_single_column():
    lines = [
        {
            "words": [
                {"x0": 10.0, "x1": 30.0},
                {"x0": 33.0, "x1": 53.0},
                {"x0": 56.0, "x1": 76.0},
            ]
        }
    ]

    boundaries = LayoutParser._detect_column_boundaries(lines)

    assert boundaries == []


def test_split_words_into_columns_buckets_by_gutter():
    words = [
        {"x0": 10.0, "x1": 30.0, "text": "A"},
        {"x0": 33.0, "x1": 53.0, "text": "B"},
        {"x0": 300.0, "x1": 320.0, "text": "C"},
    ]

    columns = LayoutParser._split_words_into_columns(words, [176.5])

    assert len(columns) == 2
    assert [word["text"] for word in columns[0]] == ["A", "B"]
    assert [word["text"] for word in columns[1]] == ["C"]


def test_split_words_into_columns_without_boundaries_returns_single_column():
    words = [{"x0": 10.0, "x1": 30.0, "text": "A"}]

    columns = LayoutParser._split_words_into_columns(words, [])

    assert columns == [words]


def test_parse_pdf_two_columns_produces_two_text_blocks():
    parser = LayoutParser()
    pdf = _build_minimal_pdf(
        [
            (72, 720, "Alpha"),
            (120, 720, "Beta"),
            (380, 720, "Gamma"),
            (428, 720, "Delta"),
        ]
    )

    blocks = parser.parse_pdf(pdf)
    text_blocks = [b for b in blocks if b.block_type == BLOCK_TYPE_TEXT]

    assert len(text_blocks) == 2
    assert text_blocks[0].metadata["column_index"] == 0
    assert text_blocks[1].metadata["column_index"] == 1
    assert "Alpha" in text_blocks[0].text
    assert "Gamma" in text_blocks[1].text
    assert text_blocks[0].bbox[0] < text_blocks[1].bbox[0]
