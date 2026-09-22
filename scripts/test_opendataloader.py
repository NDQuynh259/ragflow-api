import sys
import time
from collections import Counter
from pathlib import Path

# Ensure UTF-8 output on Windows console
sys.stdout.reconfigure(encoding="utf-8")

# Add packages to sys.path
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / "packages" / "rag-contracts" / "src"))
sys.path.insert(0, str(root / "packages" / "rag-document-pipeline" / "src"))
sys.path.insert(0, str(root / "packages" / "rag-core" / "src"))

from rag_document_pipeline.parsers.opendataloader import OpenDataLoaderParser


def test_parse(pdf_path_str: str):
    pdf_path = Path(pdf_path_str)
    if not pdf_path.exists():
        print(f"ERROR: File not found: {pdf_path}")
        return

    print("=== Testing OpenDataLoaderParser ===")
    print(f"File: {pdf_path.name}")
    print(f"File size: {pdf_path.stat().st_size / 1024 / 1024:.2f} MB")

    output_dir = root / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    image_dir = output_dir / f"{pdf_path.stem}_images"

    content = pdf_path.read_bytes()
    parser = OpenDataLoaderParser()

    print("\nStarting parsing with opendataloader-pdf...")
    start_time = time.perf_counter()
    try:
        elements = parser.parse(content, filename=pdf_path.name, image_dir=image_dir)
        elapsed = time.perf_counter() - start_time
    except Exception as e:
        print(f"Parsing failed with error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return

    print(f"\n Parsing completed in {elapsed:.2f} seconds!")
    print(f"Total LayoutElements extracted: {len(elements)}")

    # Breakdown by element type
    type_counter = Counter(el.type for el in elements)
    print("\n--- Elements by Type ---")
    for el_type, count in type_counter.most_common():
        print(f"  {el_type:20s}: {count:4d}")

    # Breakdown by page
    page_counter = Counter(el.page_number for el in elements)
    print(f"\nTotal pages with elements: {len(page_counter)}")
    print(f"Page range: {min(page_counter.keys())} -> {max(page_counter.keys())}")

    # Sample elements from first 3 pages
    print("\n--- Sample Extracted Content (First 5 elements) ---")
    for i, el in enumerate(elements[:5]):
        print(f"\n[{i+1}] Page {el.page_number} | Type: {el.type} | BBox: {el.bbox}")
        preview = el.text.replace("\n", " ")[:150]
        print(f"    Text: {preview}{'...' if len(el.text) > 150 else ''}")
        if el.metadata:
            print(f"    Metadata: {el.metadata}")

    # Check for images and report saved image files
    image_elements = [el for el in elements if el.type in ("image", "figure")]
    print(f"\n--- Extracted Images: {len(image_elements)} ---")
    if image_dir.exists():
        saved_images = list(image_dir.glob("*"))
        print(f"Saved {len(saved_images)} image files to: {image_dir}")
        for img_file in saved_images:
            size_kb = img_file.stat().st_size / 1024
            print(f"  - {img_file.name} ({size_kb:.1f} KB)")
    for i, img in enumerate(image_elements):
        uri = img.image_data.uri if img.image_data else img.source
        print(f"  [Image {i+1}] Page {img.page_number} | BBox: {img.bbox} | URI: {uri}")

    # Check for tables
    tables = [el for el in elements if el.type in ("table", "data_table")]
    print(f"\n--- Tables found: {len(tables)} ---")
    for i, tbl in enumerate(tables[:3]):
        print(f"\n[Table {i+1}] Page {tbl.page_number} | BBox: {tbl.bbox}")
        if tbl.table_data:
            print(f"    Headers: {tbl.table_data.headers}")
            print(f"    Data rows: {len(tbl.table_data.rows)} rows")
        print("    Content Preview:")
        for line in tbl.text.split("\n")[:5]:
            print(f"      {line[:120]}")

    # Check text quality & Vietnamese encoding
    sample_text = " ".join(el.text for el in elements[:20])
    vietnamese_chars = [c for c in sample_text if c in "àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđĐ"]
    print("\n--- Vietnamese Character Verification ---")
    print(f"Vietnamese accented characters detected: {len(vietnamese_chars)} occurrences")
    if vietnamese_chars:
        print(" Vietnamese accents properly preserved!")
    else:
        print(" WARNING: No Vietnamese accented characters found in sample.")

    # Export full parsed elements to JSON
    all_elements_dump = [el.model_dump() for el in elements]

    # Generate Markdown preview
    md_lines = [f"# {pdf_path.stem}\n"]
    for el in elements:
        if el.type == "heading":
            level = el.heading_level or 2
            prefix = "#" * max(1, min(6, level))
            md_lines.append(f"\n{prefix} {el.text}\n")
        elif el.type in ("image", "figure"):
            img_uri = el.image_data.uri if el.image_data and el.image_data.uri else (el.source or "")
            cap = (el.image_data.caption if el.image_data else None) or el.caption or "Hình ảnh"
            # Use relative path for markdown
            img_rel = Path(img_uri).name if img_uri else ""
            img_folder = f"{pdf_path.stem}_images"
            md_lines.append(f"\n![{cap}]({img_folder}/{img_rel})\n*{cap}*\n")
        elif el.type in ("table", "data_table"):
            md_lines.append("\n" + el.text + "\n")
        elif el.type == "caption":
            md_lines.append(f"\n*{el.text}*\n")
        else:
            md_lines.append(f"\n{el.text}\n")
    md_content = "".join(md_lines)

    import json
    import shutil

    target_dirs = [root / "output", root / "outputs"]
    for out_dir in target_dirs:
        out_dir.mkdir(parents=True, exist_ok=True)

        # Copy images if saving to a different directory than source image_dir
        dest_img_dir = out_dir / f"{pdf_path.stem}_images"
        if dest_img_dir.resolve() != image_dir.resolve():
            dest_img_dir.mkdir(parents=True, exist_ok=True)
            if image_dir.exists():
                for img_file in image_dir.glob("*"):
                    shutil.copy2(img_file, dest_img_dir / img_file.name)

        output_summary = {
            "filename": pdf_path.name,
            "elapsed_seconds": round(elapsed, 2),
            "total_elements": len(elements),
            "type_breakdown": dict(type_counter),
            "page_count": len(page_counter),
            "pages": dict(sorted(page_counter.items())),
            "images_directory": str(dest_img_dir.as_posix()),
            "elements": all_elements_dump,
        }

        # Save files
        (out_dir / f"{pdf_path.stem}_summary.json").write_text(json.dumps(output_summary, ensure_ascii=False, indent=2), encoding="utf-8")
        (out_dir / f"{pdf_path.stem}_elements.json").write_text(json.dumps(all_elements_dump, ensure_ascii=False, indent=2), encoding="utf-8")
        (out_dir / f"{pdf_path.stem}.md").write_text(md_content, encoding="utf-8")
        (out_dir / "parse_test_result.json").write_text(json.dumps(output_summary, ensure_ascii=False, indent=2), encoding="utf-8")
        (out_dir / "parsed_elements.json").write_text(json.dumps(all_elements_dump, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"\n Exported to: {out_dir}")
        print(f"  - {out_dir / f'{pdf_path.stem}.md'}")
        print(f"  - {out_dir / f'{pdf_path.stem}_elements.json'}")
        print(f"  - {out_dir / f'{pdf_path.stem}_summary.json'}")
        print(f"  - {dest_img_dir} ({len(list(dest_img_dir.glob('*')))} images)")

if __name__ == "__main__":
    default_path = (
        r"C:\Users\Admin\Downloads\sop_la_gi_vnce_co_hinh_anh_bitmap.pdf"
        if Path(r"C:\Users\Admin\Downloads\sop_la_gi_vnce_co_hinh_anh_bitmap.pdf").exists()
        else r"C:\Users\ndquynh\Downloads\sop_la_gi_vnce_co_hinh_anh_bitmap.pdf"
    )
    target_file = sys.argv[1] if len(sys.argv) > 1 else default_path
    test_parse(target_file)
