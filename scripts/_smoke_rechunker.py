"""Smoke test for the rechunker module (not part of the test suite)."""
import json
import os
import sys
import tempfile

sys.path.insert(0, "packages/rag-contracts/src")
sys.path.insert(0, "packages/rag-document-pipeline/src")

from rag_document_pipeline.models import LayoutElement
from rag_document_pipeline.rechunker import (
    HeadingAwareChunker,
    LayoutNormalizer,
    Rechunker,
    SemanticTextChunker,
)

s = SemanticTextChunker()
sentences = s._split_sentences(
    "Giá trị là 1.500.000 đồng. ThS. Nguyễn nói v.v. rằng đạt 85%. Bảng 1 cho kết quả."
)
print("sentences:", sentences)
assert len(sentences) == 3, sentences
assert "1.500.000" in sentences[0]
assert "ThS." in sentences[1]

print("jaccard:", round(s._jaccard_distance("a b c", "b c d"), 3))
assert abs(s._jaccard_distance("a b c", "b c d") - 0.5) < 1e-9

print("thresholds:", [round(s._calculate_threshold(d), 3) for d in ([], [0.1, 0.5, 0.9], [0.2, 0.4])])

# Markdown table lines stay atomic
tbl = s._split_sentences("Intro here.\n| a | b |\n| --- | --- |\n| 1 | 2 |\nOutro.")
assert any(line.startswith("|") for line in tbl), tbl

uri = tempfile.mktemp(suffix=".json")
payload = {
    "elements": [
        {"id": "h1", "type": "heading", "text": "CHƯƠNG I", "page_number": 1, "heading_level": 1},
        {
            "id": "p1",
            "type": "paragraph",
            "text": "Điều 1. Phạm vi áp dụng rộng rãi cho toàn bộ cơ quan. Điều 2. Không áp dụng trường hợp sau đây. Điều 3. Các quy định khác.",
            "page_number": 1,
        },
        {"id": "c1", "type": "caption", "text": "Bảng 1: Kết quả kinh doanh 2025", "page_number": 1},
        {
            "id": "t1",
            "type": "table",
            "page_number": 1,
            "text": "",
            "table_data": {"headers": ["Chỉ tiêu", "Q1"], "rows": [["Doanh thu", "100"], ["Lợi nhuận", "20"]]},
        },
        {"id": "f1", "type": "footer", "text": "Trang 1", "page_number": 1},
    ]
}
with open(uri, "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False)


class FakeStorage:
    def get(self, u):
        with open(u, "rb") as f:
            return f.read()


chunks = Rechunker(FakeStorage()).rechunk(uri, document_id="doc-1", chunk_size=400)
for c in chunks:
    print(c.index, c.kind, repr(c.content[:50]), c.section_path)
assert all("Trang 1" not in c.content for c in chunks), "footer must be skipped"
assert any(c.kind == "table" and "Bảng 1" in c.content for c in chunks), "caption bound to table"
assert all(c.section_path == ["CHƯƠNG I"] for c in chunks if c.kind == "text"), "section propagation"
assert [c.index for c in chunks] == list(range(len(chunks))), "sequential indices"

# Caption binding directly
els = [LayoutElement.model_validate(payload["elements"][i]) for i in (2, 3)]
norm = LayoutNormalizer.normalize(els)
assert norm[0].caption == "Bảng 1: Kết quả kinh doanh 2025"
print("bound caption:", norm[0].caption)

os.unlink(uri)
print("ALL_CHECKS_PASSED")
