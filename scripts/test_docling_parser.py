"""Test DoclingParser: parse PDF with Docling + OCR, separate into text/table/image, and export to JSON.

Usage:
    python scripts/test_docling_parser.py [path_to_pdf] [output_json_path]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Add package paths to sys.path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT / "packages" / "rag-document-pipeline" / "src"))
sys.path.insert(0, str(WORKSPACE_ROOT / "packages" / "rag-contracts" / "src"))

# Ensure utf-8 stdout on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from rag_document_pipeline.models import ElementType, LayoutElement, ParsedDocument
from rag_document_pipeline.parsers.docling import DoclingParser
from rag_document_pipeline.pipeline import DocumentPipeline


DEFAULT_PDF_PATH = Path(
    r"C:\Users\Admin\.gemini\antigravity-ide\brain\c8581da7-12f9-4fe9-87cb-78215f811202\.user_uploaded\media_1789117553183.pdf"
)
DEFAULT_OUTPUT_JSON = WORKSPACE_ROOT / "output" / "docling_parsed_result.json"


def serialize_element(element: LayoutElement) -> dict:
    """Convert LayoutElement to clean dictionary for JSON serialization."""
    data = {
        "id": element.id,
        "type": element.type,
        "text": element.text,
        "page_number": element.page_number,
        "bbox": element.bbox,
        "order": element.order,
        "heading_level": element.heading_level,
        "section_path": element.section_path,
        "metadata": element.metadata,
    }
    if element.table_data:
        rows = element.table_data.rows
        headers = element.table_data.headers
        num_cols = len(headers) if headers else (len(rows[0]) if rows else 0)
        data["table_data"] = {
            "headers": headers,
            "rows": rows,
            "num_rows": len(rows),
            "num_cols": num_cols,
            "caption": element.table_data.caption,
        }
    if element.image_data:
        data["image_data"] = {
            "uri": element.image_data.uri,
            "caption": element.image_data.caption,
            "caption_refs": element.image_data.caption_refs,
            "ocr_text": element.image_data.ocr_text,
            "description": element.image_data.description,
        }
    return data


def run_parse_test(
    pdf_path: Path,
    output_json_path: Path,
    *,
    do_ocr: bool = True,
):
    print(f"=" * 60)
    print(f"Testing DoclingParser (OCR={do_ocr})")
    print(f"Input file : {pdf_path}")
    print(f"Output JSON: {output_json_path}")
    print(f"=" * 60)

    if not pdf_path.exists():
        print(f"Error: PDF file does not exist: {pdf_path}")
        sys.exit(1)

    content = pdf_path.read_bytes()
    filename = pdf_path.name
    print(f"File size: {len(content):,} bytes")

    # 1. Initialize DoclingParser
    print("\n[1/3] Initializing DoclingParser...")
    parser = DoclingParser(do_ocr=do_ocr)

    # 2. Parse and separate via DocumentPipeline
    print("[2/3] Parsing PDF and separating content into text / table / image...")
    start_time = time.perf_counter()
    pipeline = DocumentPipeline(parser=parser)
    parsed_doc = pipeline.parse_and_separate(
        content,
        filename=filename,
        document_id="docling-test-sop-2026",
    )
    elapsed = time.perf_counter() - start_time
    print(f"Parsing completed in {elapsed:.2f} seconds.")

    # 3. Print Summary
    print("\n" + "=" * 60)
    print("PARSING SUMMARY")
    print("=" * 60)
    print(f"Total elements : {len(parsed_doc.all_elements)}")
    print(f"Page count     : {parsed_doc.page_count}")
    print(f"Text elements  : {len(parsed_doc.text_elements)}")
    print(f"Table elements : {len(parsed_doc.table_elements)}")
    print(f"Image elements : {len(parsed_doc.image_elements)}")

    # Preview Text elements
    print("\n--- SAMPLE TEXT ELEMENTS (First 5) ---")
    for el in parsed_doc.text_elements[:5]:
        preview = el.text.replace("\n", " ")[:90]
        hl = f" (H{el.heading_level})" if el.heading_level else ""
        print(f"  [p.{el.page_number} {el.type}{hl}]: {preview}...")

    # Preview Table elements
    print(f"\n--- TABLE ELEMENTS ({len(parsed_doc.table_elements)}) ---")
    for i, tbl in enumerate(parsed_doc.table_elements, 1):
        print(f"\n  [Table {i} - Page {tbl.page_number}]")
        if tbl.table_data:
            rows = tbl.table_data.rows
            headers = tbl.table_data.headers
            num_cols = len(headers) if headers else (len(rows[0]) if rows else 0)
            print(f"  Dimensions: {len(rows)} rows x {num_cols} cols")
            if headers:
                print(f"  Headers: {headers}")
        print("  Markdown Preview:")
        for line in tbl.text.split("\n")[:4]:
            print(f"    {line}")
        if len(tbl.text.split("\n")) > 4:
            print("    ...")

    # Preview Image elements
    print(f"\n--- IMAGE / FIGURE ELEMENTS ({len(parsed_doc.image_elements)}) ---")
    for i, img in enumerate(parsed_doc.image_elements, 1):
        cap = (img.image_data.caption if img.image_data else "") or "(no caption)"
        print(f"  [Image {i} - Page {img.page_number}]: {cap}")
        if img.bbox:
            print(f"    bbox: {img.bbox}")

    # 4. Serialize to JSON
    output_data = {
        "document_id": parsed_doc.document_id,
        "filename": parsed_doc.filename,
        "page_count": parsed_doc.page_count,
        "parser_metadata": parsed_doc.metadata,
        "parsing_time_seconds": round(elapsed, 2),
        "counts": {
            "total": len(parsed_doc.all_elements),
            "text": len(parsed_doc.text_elements),
            "table": len(parsed_doc.table_elements),
            "image": len(parsed_doc.image_elements),
        },
        "separated": {
            "text": [serialize_element(el) for el in parsed_doc.text_elements],
            "table": [serialize_element(el) for el in parsed_doc.table_elements],
            "image": [serialize_element(el) for el in parsed_doc.image_elements],
        },
        "all_elements": [serialize_element(el) for el in parsed_doc.all_elements],
    }

    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"\n[3/3] Successfully exported JSON result to:")
    print(f"      {output_json_path}")
    print(f"      File size: {output_json_path.stat().st_size:,} bytes")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test DoclingParser with JSON export")
    parser.add_argument("pdf", nargs="?", default=str(DEFAULT_PDF_PATH), help="Path to PDF file")
    parser.add_argument("output", nargs="?", default=str(DEFAULT_OUTPUT_JSON), help="Output JSON path")
    parser.add_argument("--no-ocr", action="store_true", help="Disable OCR")
    args = parser.parse_args()

    run_parse_test(
        pdf_path=Path(args.pdf),
        output_json_path=Path(args.output),
        do_ocr=not args.no_ocr,
    )
