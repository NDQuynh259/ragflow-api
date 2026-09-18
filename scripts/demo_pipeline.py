"""End-to-end demo: PDF → Parse → Chunk → Embed → Store → Query.

Usage:
    python scripts/demo_pipeline.py <path-to-pdf> [query]

Examples:
    python scripts/demo_pipeline.py document.pdf
    python scripts/demo_pipeline.py document.pdf "SOP là gì?"
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Load .env before anything else
from dotenv import load_dotenv

load_dotenv()


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts/demo_pipeline.py <PDF_PATH> [QUERY]")
        print('Example: python scripts/demo_pipeline.py doc.pdf "SOP là gì?"')
        return 2

    pdf_path = Path(sys.argv[1])
    if not pdf_path.exists():
        print(f"File not found: {pdf_path}")
        return 1

    query = sys.argv[2] if len(sys.argv) > 2 else None

    print("=" * 60)
    print("  RAG Pipeline Demo")
    print("=" * 60)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    # Setup output and images directories
    document_id = pdf_path.stem
    content = pdf_path.read_bytes()
    output_dir = Path("output") / document_id
    output_dir.mkdir(parents=True, exist_ok=True)
    image_dir = output_dir / "images"
    image_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Step 1: Parse PDF and separate by type
    # ------------------------------------------------------------------
    print(f"\n📄 [1/5] Parsing PDF: {pdf_path.name}")
    from rag_document_pipeline import DocumentPipeline

    pipeline = DocumentPipeline()

    # Show intermediate result — parsed and separated
    parsed = pipeline.parse_and_separate(
        content, filename=pdf_path.name, document_id=document_id, image_dir=image_dir
    )
    print(f"   ✅ Pages: {parsed.page_count}")
    print(f"   📝 Text elements:  {len(parsed.text_elements)}")
    print(f"   📊 Table elements: {len(parsed.table_elements)}")
    print(f"   🖼️  Image elements: {len(parsed.image_elements)}")
    print(f"   📦 Total elements: {len(parsed.all_elements)}")

    # ------------------------------------------------------------------
    # Step 2: Type-aware chunking
    # ------------------------------------------------------------------
    print("\n✂️  [2/5] Chunking by type (text/table/image)...")
    result = pipeline.process(
        content, filename=pdf_path.name, document_id=document_id, image_dir=image_dir
    )

    text_chunks = [c for c in result.chunks if c.kind == "text"]
    table_chunks = [c for c in result.chunks if c.kind == "table"]
    figure_chunks = [c for c in result.chunks if c.kind == "figure"]
    indexable = [c for c in result.chunks if c.indexable]

    print(f"   ✅ Total chunks: {len(result.chunks)}")
    print(f"      📝 Text:   {len(text_chunks)}")
    print(f"      📊 Table:  {len(table_chunks)}")
    print(f"      🖼️  Figure: {len(figure_chunks)}")
    print(f"      🔍 Indexable: {len(indexable)}")

    # Save chunks to file for inspection
    chunks_file = output_dir / "chunks.json"
    chunks_data = [c.model_dump(mode="json") for c in result.chunks]
    chunks_file.write_text(
        json.dumps(chunks_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"   💾 Chunks saved: {chunks_file}")

    # Print sample chunks
    print("\n   --- Sample chunks ---")
    for chunk in result.chunks[:3]:
        preview = chunk.content[:120].replace("\n", " ")
        print(
            f"   [{chunk.kind:6s}] page {chunk.page_start}: {preview}..."
        )

    # ------------------------------------------------------------------
    # Step 3: Embed and index
    # ------------------------------------------------------------------
    print("\n🧠 [3/5] Embedding and indexing into pgvector...")
    try:
        from rag_core.engine import RAGEngine

        engine = RAGEngine.from_env()
        count = engine.index(result.chunks)
        print(f"   ✅ Indexed {count} chunks into PostgreSQL + pgvector")
    except Exception as exc:
        print(f"   ⚠️  Indexing failed: {exc}")
        print("   💡 Make sure PostgreSQL is running:")
        print("      docker compose -f deploy/docker-compose.yml up -d")
        return 1

    # ------------------------------------------------------------------
    # Step 4: Query (if provided)
    # ------------------------------------------------------------------
    if query:
        print(f'\n🔍 [4/5] Retrieving context for: "{query}"')
        results = engine.retrieval.retrieve(
            query, document_ids=[document_id]
        )
        print(f"   ✅ Retrieved {len(results)} relevant chunks")
        for i, sr in enumerate(results):
            preview = sr.chunk.content[:100].replace("\n", " ")
            print(
                f"   #{i + 1} [{sr.chunk.kind}] "
                f"page {sr.chunk.page_start} "
                f"(score: {sr.score:.3f}): {preview}..."
            )

        # ------------------------------------------------------------------
        # Step 5: Generate answer
        # ------------------------------------------------------------------
        print("\n💬 [5/5] Generating answer...")
        gen_result = engine.generation.generate(query, results)
        print(f"\n{'─' * 60}")
        print(f"   Câu hỏi: {query}")
        print(f"{'─' * 60}")
        print("   Trả lời:\n")
        print(f"   {gen_result.answer}")
        print(f"\n{'─' * 60}")

        if gen_result.citations:
            print(f"   📌 Citations ({len(gen_result.citations)}):")
            for cit in gen_result.citations:
                print(
                    f"      - Chunk {cit.chunk_id[:8]}... "
                    f"| Trang {cit.page_number}"
                )

        if gen_result.usage:
            print(f"   📊 Token usage: {gen_result.usage}")
    else:
        print("\n💡 To query, run:")
        print(
            f'   python scripts/demo_pipeline.py "{pdf_path}" "Câu hỏi?"'
        )

    print(f"\n{'=' * 60}")
    print("  Done!")
    print(f"{'=' * 60}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
