"""Unit tests for the LayoutParser (multimodal layout segmentation with Unstructured)."""

from types import SimpleNamespace
from unittest.mock import MagicMock
import unittest

from app.ingestion.parsers.layout_parser import (
    BLOCK_TYPE_IMAGE,
    BLOCK_TYPE_TABLE,
    BLOCK_TYPE_TEXT,
    LayoutBlock,
    LayoutParseError,
    LayoutParser,
)


class _MockCoordinates:
    def __init__(self, points):
        self.points = points


class _MockMetadata:
    def __init__(
        self,
        page_number=1,
        coordinates=None,
        text_as_html=None,
        image_path=None,
        filename="test.pdf",
    ):
        self.page_number = page_number
        self.coordinates = coordinates
        self.text_as_html = text_as_html
        self.image_path = image_path
        self.filename = filename


class _MockElement:
    def __init__(self, text, category="NarrativeText", metadata=None, element_id=None):
        self.text = text
        self.category = category
        self.metadata = metadata or _MockMetadata()
        self.id = element_id or "elem-123"


class TestLayoutParser(unittest.TestCase):
    def test_parse_pdf_raises_when_unstructured_missing(self):
        import app.ingestion.parsers.layout_parser as layout_module

        original_partition_pdf = layout_module.partition_pdf
        try:
            layout_module.partition_pdf = None
            with self.assertRaises(LayoutParseError) as ctx:
                LayoutParser().parse_pdf(b"%PDF-1.4")
            self.assertIn("unstructured", str(ctx.exception))
        finally:
            layout_module.partition_pdf = original_partition_pdf

    def test_elements_to_blocks_converts_text_elements(self):
        parser = LayoutParser()
        coords = _MockCoordinates([(10.0, 20.0), (100.0, 20.0), (100.0, 50.0), (10.0, 50.0)])
        meta = _MockMetadata(page_number=1, coordinates=coords)

        elements = [
            _MockElement("Document Title", category="Title", metadata=meta),
            _MockElement("This is a paragraph of narrative text.", category="NarrativeText", metadata=meta),
            _MockElement("Bullet item 1", category="ListItem", metadata=meta),
        ]

        blocks = parser._elements_to_blocks(elements)

        self.assertEqual(len(blocks), 3)
        self.assertTrue(all(b.block_type == BLOCK_TYPE_TEXT for b in blocks))
        self.assertEqual(blocks[0].text, "Document Title")
        self.assertEqual(blocks[0].metadata["category"], "Title")
        self.assertEqual(blocks[0].bbox, (10.0, 20.0, 100.0, 50.0))
        self.assertEqual(blocks[1].text, "This is a paragraph of narrative text.")
        self.assertEqual(blocks[2].text, "Bullet item 1")

    def test_elements_to_blocks_converts_table_with_html(self):
        parser = LayoutParser()
        html = (
            "<table>"
            "<tr><th>Name</th><th>Role</th></tr>"
            "<tr><td>Alice</td><td>Admin</td></tr>"
            "<tr><td>Bob</td><td>User</td></tr>"
            "</table>"
        )
        coords = _MockCoordinates([(0.0, 100.0), (200.0, 100.0), (200.0, 200.0), (0.0, 200.0)])
        meta = _MockMetadata(page_number=2, coordinates=coords, text_as_html=html)

        elements = [
            _MockElement("Name Role\nAlice Admin\nBob User", category="Table", metadata=meta),
        ]

        blocks = parser._elements_to_blocks(elements)

        self.assertEqual(len(blocks), 1)
        table_block = blocks[0]
        self.assertEqual(table_block.block_type, BLOCK_TYPE_TABLE)
        self.assertEqual(table_block.page_number, 2)
        self.assertEqual(table_block.bbox, (0.0, 100.0, 200.0, 200.0))
        self.assertEqual(
            table_block.rows,
            [
                ["Name", "Role"],
                ["Alice", "Admin"],
                ["Bob", "User"],
            ],
        )
        self.assertIn("| Name | Role |", table_block.text)
        self.assertIn("| Alice | Admin |", table_block.text)
        self.assertIn("| Bob | User |", table_block.text)

    def test_elements_to_blocks_converts_table_fallback_plain_text(self):
        parser = LayoutParser()
        coords = _MockCoordinates([(10.0, 10.0), (100.0, 10.0), (100.0, 60.0), (10.0, 60.0)])
        meta = _MockMetadata(page_number=1, coordinates=coords, text_as_html=None)

        plain_table_text = "Col1\tCol2\nVal1\tVal2"
        elements = [
            _MockElement(plain_table_text, category="Table", metadata=meta),
        ]

        blocks = parser._elements_to_blocks(elements)

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].block_type, BLOCK_TYPE_TABLE)
        self.assertEqual(blocks[0].rows, [["Col1", "Col2"], ["Val1", "Val2"]])
        self.assertIn("| Col1 | Col2 |", blocks[0].text)

    def test_elements_to_blocks_converts_image_blocks(self):
        parser = LayoutParser()
        coords = _MockCoordinates([(50.0, 50.0), (150.0, 50.0), (150.0, 150.0), (50.0, 150.0)])
        meta = _MockMetadata(page_number=3, coordinates=coords, image_path="/path/to/chart.png")

        elements = [
            _MockElement("Figure 1: Architecture Diagram", category="Image", metadata=meta),
            _MockElement("Figure Caption Details", category="FigureCaption", metadata=meta),
        ]

        blocks = parser._elements_to_blocks(elements)

        self.assertEqual(len(blocks), 2)
        self.assertTrue(all(b.block_type == BLOCK_TYPE_IMAGE for b in blocks))
        self.assertEqual(blocks[0].image_name, "/path/to/chart.png")
        self.assertEqual(blocks[0].page_number, 3)
        self.assertEqual(blocks[0].bbox, (50.0, 50.0, 150.0, 150.0))

    def test_layout_block_to_dict_drops_image_bytes(self):
        block = LayoutBlock(
            block_type=BLOCK_TYPE_IMAGE,
            page_number=2,
            bbox=(1.0, 2.0, 3.0, 4.0),
            image_bytes=b"\x89PNG",
            image_name="Im0",
        )

        payload = block.to_dict()

        self.assertNotIn("image_bytes", payload)
        self.assertEqual(payload["image_size"], 4)
        self.assertEqual(payload["bbox"], [1.0, 2.0, 3.0, 4.0])
        self.assertEqual(payload["page_number"], 2)

    def test_sanitize_text_cleans_control_characters(self):
        raw = "Hello\x00\x08World\r\nLine 2\tEnd"
        cleaned = LayoutParser.sanitize_text(raw)
        self.assertNotIn("\x00", cleaned)
        self.assertNotIn("\x08", cleaned)
        self.assertIn("Hello", cleaned)
        self.assertIn("Line 2", cleaned)
        self.assertIn("\t", cleaned)
        self.assertIn("\n", cleaned)

    def test_rows_to_markdown_empty_returns_empty_string(self):
        self.assertEqual(LayoutParser._rows_to_markdown([]), "")

    def test_rows_to_markdown_escapes_markdown_delimiters(self):
        markdown = LayoutParser._rows_to_markdown([["A|B", "Line\nBreak"]])
        self.assertIn(r"A\|B", markdown)
        self.assertIn("Line<br>Break", markdown)

    def test_sort_blocks_by_page_and_top_left(self):
        b1 = LayoutBlock(block_type=BLOCK_TYPE_TEXT, page_number=2, bbox=(10.0, 20.0, 50.0, 40.0), text="Page2")
        b2 = LayoutBlock(block_type=BLOCK_TYPE_TEXT, page_number=1, bbox=(10.0, 100.0, 50.0, 120.0), text="Page1-Bottom")
        b3 = LayoutBlock(block_type=BLOCK_TYPE_TEXT, page_number=1, bbox=(10.0, 20.0, 50.0, 40.0), text="Page1-Top")

        sorted_blocks = LayoutParser._sort_blocks([b1, b2, b3])
        self.assertEqual(sorted_blocks[0].text, "Page1-Top")
        self.assertEqual(sorted_blocks[1].text, "Page1-Bottom")
        self.assertEqual(sorted_blocks[2].text, "Page2")

    def test_parse_pdf_uses_partition_pdf_mock(self):
        import app.ingestion.parsers.layout_parser as layout_module

        original_partition_pdf = layout_module.partition_pdf
        try:
            mock_partition_pdf = MagicMock()
            mock_partition_pdf.return_value = [
                _MockElement("Parsed text content", category="NarrativeText")
            ]
            layout_module.partition_pdf = mock_partition_pdf

            parser = LayoutParser()
            blocks = parser.parse_pdf(b"%PDF-sample", strategy="auto")

            self.assertTrue(mock_partition_pdf.called)
            self.assertEqual(len(blocks), 1)
            self.assertEqual(blocks[0].text, "Parsed text content")
            self.assertEqual(blocks[0].block_type, BLOCK_TYPE_TEXT)
        finally:
            layout_module.partition_pdf = original_partition_pdf

    def test_parse_pdf_fallback_to_fast_on_error(self):
        import app.ingestion.parsers.layout_parser as layout_module

        original_partition_pdf = layout_module.partition_pdf
        try:
            call_strategies = []

            def mock_partition_pdf(file, strategy="auto", **kwargs):
                call_strategies.append(strategy)
                if strategy == "auto":
                    raise RuntimeError("OCR or detectron2 missing")
                return [_MockElement("Fallback fast text", category="NarrativeText")]

            layout_module.partition_pdf = mock_partition_pdf

            parser = LayoutParser()
            blocks = parser.parse_pdf(b"%PDF-sample", strategy="auto")

            self.assertEqual(call_strategies, ["auto", "fast"])
            self.assertEqual(len(blocks), 1)
            self.assertEqual(blocks[0].text, "Fallback fast text")
        finally:
            layout_module.partition_pdf = original_partition_pdf

    def test_parse_non_pdf_unsupported_format(self):
        import app.ingestion.parsers.layout_parser as layout_module

        original_partition = layout_module.partition
        try:
            layout_module.partition = None
            parser = LayoutParser()

            with self.assertRaises(LayoutParseError) as ctx:
                parser.parse(b"dummy", "file.xyz")
            self.assertIn("PDF files only", str(ctx.exception))
        finally:
            layout_module.partition = original_partition


if __name__ == "__main__":
    unittest.main()
