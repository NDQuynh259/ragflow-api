"""Script to parse a document and output structured layout blocks using LayoutParser (Unstructured).

Usage:
    python scripts/test_parse_file.py <path_to_document_or_pdf> [--output output.json] [--strategy auto|fast|hi_res]

Example:
    python scripts/test_parse_file.py sample.pdf --output result.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ingestion.parsers.layout_parser import LayoutBlock, LayoutParseError, LayoutParser


def parse_and_report(
    file_path: str | Path,
    output_json_path: str | Path | None = None,
    strategy: str = "auto",
) -> list[LayoutBlock]:
    """Read a document file, parse it into LayoutBlocks, and print summary."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path.resolve()}")

    print(f"=== [LayoutParser] Parsing file: {path.name} ===")
    print(f"File Size: {path.stat().st_size:,} bytes")
    print(f"Strategy:  {strategy}")

    with open(path, "rb") as f:
        file_bytes = f.read()

    parser = LayoutParser()
    try:
        if path.suffix.lower() == ".pdf":
            blocks = parser.parse_pdf(file_bytes, strategy=strategy)
        else:
            blocks = parser.parse(file_bytes, filename=path.name)
    except LayoutParseError as exc:
        print(f"\n[ERROR] LayoutParseError: {exc}")
        raise
    except Exception as exc:
        print(f"\n[ERROR] Unexpected error during parsing: {exc}")
        raise

    # Summary statistics
    total_blocks = len(blocks)
    text_blocks = [b for b in blocks if b.block_type == "text"]
    table_blocks = [b for b in blocks if b.block_type == "table"]
    image_blocks = [b for b in blocks if b.block_type == "image"]

    print("\n--- Parsing Summary ---")
    print(f"Total Blocks: {total_blocks}")
    print(f"  - Text Blocks:  {len(text_blocks)}")
    print(f"  - Table Blocks: {len(table_blocks)}")
    print(f"  - Image Blocks: {len(image_blocks)}")

    print("\n--- Detailed Layout Blocks ---")
    for idx, block in enumerate(blocks, start=1):
        print(f"\n[Block #{idx}] Type: {block.block_type.upper()} | Page: {block.page_number} | BBox: {block.bbox}")
        if block.metadata:
            print(f"  Metadata: {json.dumps(block.metadata, ensure_ascii=False)}")
        if block.block_type == "text":
            preview = block.text[:150].replace("\n", " ") + ("..." if len(block.text) > 150 else "")
            print(f"  Text Content: {preview}")
        elif block.block_type == "table":
            print(f"  Rows Count: {len(block.rows or [])}")
            print(f"  Markdown Preview:\n{block.text}")
        elif block.block_type == "image":
            print(f"  Image Name: {block.image_name}")
            if block.text:
                print(f"  Caption: {block.text}")

    # Output JSON file if requested
    if output_json_path:
        out_path = Path(output_json_path)
        payload = [b.to_dict() for b in blocks]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        print(f"\n[Output] Full structured JSON exported to: {out_path.resolve()}")

    return blocks


def _create_sample_demo_pdf(output_path: Path) -> Path:
    """Create a minimal valid PDF for demonstration/testing."""
    content_stream = "BT /F1 14 Tf 72 720 Td (Demo PDF Document for LayoutParser) Tj 0 -30 Td (Second line of sample text.) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(content_stream)).encode() + b" >>\nstream\n" + content_stream.encode() + b"\nendstream",
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
    pdf += f"trailer\n<< /Size {count} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode()

    output_path.write_bytes(pdf)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parse a document file with LayoutParser (Unstructured) and inspect structured output."
    )
    parser.add_argument(
        "file_path",
        nargs="?",
        default=None,
        help="Path to input document (PDF, etc.). If omitted, runs a demo sample.",
    )
    parser.add_argument(
        "-o",
        "--output",
        dest="output_json",
        default=None,
        help="Path to export the structured result as JSON (e.g. parsed_result.json)",
    )
    parser.add_argument(
        "-s",
        "--strategy",
        dest="strategy",
        default="auto",
        choices=["auto", "fast", "hi_res", "ocr_only"],
        help="Unstructured partition strategy (default: auto)",
    )

    args = parser.parse_args()

    if not args.file_path:
        demo_dir = Path(__file__).resolve().parent / "demo_temp"
        demo_dir.mkdir(parents=True, exist_ok=True)
        demo_pdf = demo_dir / "sample_demo.pdf"
        _create_sample_demo_pdf(demo_pdf)
        print(f"[Demo] Created sample demo PDF at: {demo_pdf}")
        output_json = args.output_json or str(demo_dir / "sample_demo_output.json")
        parse_and_report(demo_pdf, output_json_path=output_json, strategy=args.strategy)
    else:
        parse_and_report(args.file_path, output_json_path=args.output_json, strategy=args.strategy)


if __name__ == "__main__":
    main()
