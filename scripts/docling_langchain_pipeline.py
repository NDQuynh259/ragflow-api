"""Export every stage of a Docling -> LangChain PDF pipeline as JSON.

Usage: python scripts/docling_langchain_pipeline.py input.pdf outputs/docling
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def repair_text(value: str) -> str:
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


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python scripts/docling_langchain_pipeline.py INPUT.pdf OUTPUT_DIR")
        return 2
    source, output = Path(sys.argv[1]), Path(sys.argv[2])
    output.mkdir(parents=True, exist_ok=True)

    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from langchain_core.documents import Document
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    # Step 1: Docling parses text, tables, images and layout.
    # OCR is enabled because this input is a bitmap PDF. OCR only supplies the
    # text content; Docling still keeps tables and pictures as separate items.
    pdf_options = PdfPipelineOptions(do_ocr=True)
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_options)}
    )
    result = converter.convert(str(source))
    docling_doc = result.document
    raw = docling_doc.export_to_dict()
    write_json(output / "01_docling.json", raw)

    # Step 2: split the Docling model into independent modalities. Keeping page
    # and bounding-box provenance makes citations possible later.
    text_items = []
    for index, item in enumerate(raw.get("texts", [])):
        if item.get("content_layer") == "furniture":
            continue
        # `orig` is Docling's source text and is generally safer than the
        # rendered Markdown text for Vietnamese PDF content.
        value = repair_text((item.get("orig") or item.get("text") or "").strip())
        if not value:
            continue
        provenance = (item.get("prov") or [{}])[0]
        text_items.append({"id": f"text-{index}", "content": value, "type": item.get("label", "text"),
                           "page": provenance.get("page_no"), "bbox": provenance.get("bbox"),
                           "metadata": {"source": str(source), "docling_ref": item.get("self_ref")}})

    table_items = []
    for index, item in enumerate(raw.get("tables", [])):
        provenance = (item.get("prov") or [{}])[0]
        cells = (item.get("data") or {}).get("table_cells", [])
        cells = [{**c, "text": repair_text(c.get("text", ""))} for c in cells]
        table_items.append({"id": f"table-{index}", "content": "\n".join(c.get("text", "") for c in cells),
                            "cells": cells, "page": provenance.get("page_no"), "bbox": provenance.get("bbox"),
                            "metadata": {"source": str(source), "docling_ref": item.get("self_ref")}})

    image_items = []
    for index, item in enumerate(raw.get("pictures", [])):
        provenance = (item.get("prov") or [{}])[0]
        image_items.append({"id": f"image-{index}", "page": provenance.get("page_no"),
                            "bbox": provenance.get("bbox"), "caption_refs": item.get("captions", []),
                            "child_refs": item.get("children", []),
                            "metadata": {"source": str(source), "docling_ref": item.get("self_ref")}})

    write_json(output / "02_text.json", text_items)
    write_json(output / "02_tables.json", table_items)
    write_json(output / "02_images.json", image_items)

    # Step 3: send each modality through LangChain separately. Images are
    # represented by a placeholder until OCR/vision produces a description.
    records = [("text", x["content"], x) for x in text_items]
    records += [("table", x["content"], x) for x in table_items if x["content"].strip()]
    records += [("image", "[IMAGE] Vision/OCR description pending", x) for x in image_items]
    documents = [Document(page_content=content, metadata={**meta["metadata"], "kind": kind,
                    "page": meta.get("page"), "bbox": meta.get("bbox"), "source_id": meta["id"]})
                 for kind, content, meta in records]
    write_json(output / "03_langchain_documents.json", [
        {"id": meta["id"], "kind": kind, "content": content, "metadata": {**meta["metadata"],
         "page": meta.get("page"), "bbox": meta.get("bbox")}}
        for kind, content, meta in records
    ])

    # Step 4: chunk text and tables; preserve images as one record per image.
    splitter = RecursiveCharacterTextSplitter(chunk_size=1200, chunk_overlap=200)
    chunks = splitter.split_documents(documents)
    write_json(output / "04_langchain_chunks.json", [
        {"id": f"chunk-{i}", "content": chunk.page_content, "metadata": chunk.metadata}
        for i, chunk in enumerate(chunks)
    ])
    print(f"Wrote text={len(text_items)}, tables={len(table_items)}, images={len(image_items)}, chunks={len(chunks)} to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
