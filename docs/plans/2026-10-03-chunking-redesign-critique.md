# Phản biện kế hoạch chunking-redesign

- **Ngày:** 2026-10-03
- **Nhánh:** `feat/hybrid-semantic-chunking`
- **Đối tượng phản biện:**
  - `docs/plans/2026-10-03-chunking-implementation-report.md` — báo cáo triển khai hiện tại
  - `docs/plans/2026-10-03-chunking-redesign.md` — kế hoạch triển khai tiếng Việt
  - `docs/chunking-redesign/architecture-review-and-redesign-plan.md` — review kiến trúc
  - `docs/chunking-redesign/chunking-implementation-roadmap.md` — roadmap 4 tuần
- **Cơ sở kiểm chứng:** đã đọc mã nguồn thực tế `chunking/text.py`, `multimodal.py`, `table.py`, `figure.py`, `base.py`, `pipeline.py`

## Đánh giá tổng quan

Kế hoạch có **cơ sở kỹ thuật vững**, nhận diện đúng các vấn đề thực tế (provenance sai, token budget không nhất quán, reading order không deterministic, semantic boundary dễ vỡ) và đề xuất kiến trúc cải tiến hợp lý. Tuy nhiên, có **5 vấn đề** cần điều chỉnh trước khi triển khai.

---

## 🔴 Vấn đề 1: Phạm vi quá rộng, rủi ro cao — thiếu MVP thật sự

### Hiện trạng

Cả 3 plan đều mô tả dự án 4 tuần với 4-6 phases, nhưng:

- **Roadmap** yêu cầu tạo 10+ abstraction mới (CanonicalLayout, ContextBinder, Sectionizer, TokenCounter, SpanRef, RowRef, ProvenanceEntry, ChunkDiagnostic...) + thay đổi đồng thời semantic algorithm, table packing, validation logic, indexing boundary.
- **Architecture review** liệt kê 7 P0/P1 issues nhưng plan giải quyết đồng thời hết trong 4 tuần.
- **Plan 2026-10-03** có 9 tasks với checklist dài, mỗi task đòi hỏi refactor nhiều file + property-based tests.

**Thực tế production:** Một thay đổi provenance contract + canonical ordering đã đủ làm breaking change cho toàn bộ RAG pipeline. Nếu đồng thời sửa semantic splitter, table chunker, validator và indexer → risk tích lũy, rollback khó, debug phức tạp.

### Khuyến nghị

Tách thành 2 increments riêng biệt:

**Increment 1 (3-4 tuần) — Contract foundation ONLY:**

- Phase 0: Fixtures + golden baseline (P0 provenance, P0 reading order)
- Phase 1: SpanRef/ProvenanceEntry contract + derive compatibility fields
- Phase 2: Canonical reading order + cross-page sections (không thay semantic algorithm)
- Phase 3: Validation rules (fail-fast trên provenance sai, không silent repair)
- Exit criteria: Contract ổn định, provenance đúng, order deterministic, backward compatible

**Increment 2 (4-6 tuần) — Algorithm improvement:**

- Token-aware budget
- Semantic splitter nâng cao (offset-preserving, embedding validation)
- Table/figure token packing
- Migration tooling

**Lý do:** Contract phải ổn định trước khi sửa algorithm. Nếu làm cùng lúc, khi bug xuất hiện không phân biệt được do contract sai hay algorithm sai.

---

## 🔴 Vấn đề 2: Thiếu chiến lược rollback/feature flag cụ thể

### Hiện trạng

Plans đề cập "feature flags", "shadow mode", "dual-write", "config fingerprint" nhưng:

- Không có schema/enum cụ thể cho flags.
- Không có quy tắc khi nào enable/disable flag nào.
- "Shadow mode" được nhắc đến nhưng không rõ shadow output đi đâu, ai monitor, metric nào so sánh.

**Ví dụ thực tế:** nếu deploy v2 chunking với provenance mới nhưng retrieval accuracy giảm 5% → phải rollback. Nhưng nếu đã index 100K chunks v2 vào vector store thì sao?

### Khuyến nghị

Thêm section "Rollout & Rollback Contract" vào plan:

```python
# Flag schema cụ thể
class ChunkingMode(Enum):
    V1_LEGACY = "v1"           # Toàn bộ path cũ
    V2_SHADOW = "v2_shadow"     # Chạy v2, log diff, index v1
    V2_DUAL = "v2_dual"         # Index cả v1 và v2, query v1
    V2_CANARY = "v2_canary"     # 5% traffic dùng v2 index
    V2_FULL = "v2"              # Toàn bộ v2

# Rollback decision tree
if avg_retrieval_score < baseline - threshold:
    mode = V1_LEGACY
    emit_alert("chunking_v2_regression", {"score": score})
```

**Shadow metrics cần track:**

- Chunk count delta (per document)
- Provenance coverage rate (% chunks có đủ element_ids)
- Order violation count (chunk[i].source_order > chunk[i+1].source_order)
- Token overflow count (chunks > max_tokens)
- Embedding fallback rate

**Rollback SOP:**

1. Switch flag to V1_LEGACY → hiệu lực ngay, không cần deploy code.
2. Nếu đã index v2: query routing tự động về v1 namespace (do config_fingerprint khác nhau).
3. Nếu v2 records gây vấn đề storage: cleanup job thủ công (có dry-run).

---

## 🔴 Vấn đề 3: Token budget design chưa thực tế

### Hiện trạng

Plans đề xuất `TokenCounter` protocol + `TokenBudget(min_tokens, target_tokens, max_tokens, overlap_tokens, reserved_prefix_tokens)` nhưng có 3 vấn đề:

1. **Tokenizer mismatch:** Embedding model (e.g., `text-embedding-3-large`) dùng cl100k_base tokenizer, nhưng generation model dùng tokenizer khác → cùng một text có token count khác nhau.
2. **Prefix reservation:** `reserved_prefix_tokens` cho heading prefix là hợp lý trên nguyên tắc, nhưng heading có thể dài bất thường (vd: "CHƯƠNG I: QUY ĐỊNH CHUNG VỀ TỔ CHỨC BỘ MÁY, CHỨC NĂNG NHIỆM VỤ CỦA CÁC CƠ QUAN...") → reserve bao nhiêu?
3. **Overlap token không tự nhiên:** Semantic overlap nên theo sentence boundary, không cắt giữa token.

### Khuyến nghị

Đơn giản hóa budget model — dùng "token window" thay vì 5 parameters:

```python
class TokenBudget:
    """Simplified token budget với 3 tham số chính."""
    target_tokens: int = 1000      # Mục tiêu chunk size
    max_tokens: int = 1200         # Hard limit (safety margin cho model)
    overlap_sentences: int = 2     # Overlap theo số câu, không phải tokens

    # Derived — không cần config
    min_tokens: int = field(init=False)

    def __post_init__(self):
        self.min_tokens = self.target_tokens // 4  # 25% target
```

**Prefix handling:**

- Đo prefix length thực tế, **trừ ra khỏi budget** khi build chunk.
- Nếu prefix > 20% target_tokens → emit diagnostic `heading_too_long`.
- Không reserve cố định, vì heading ngắn không nên lãng phí budget.

**Multi-tokenizer strategy:**

- Primary tokenizer: embedding model's tokenizer (vì đó là hard limit thực tế).
- Validation: optional check với generation model tokenizer, chỉ emit warning nếu lệch > 10%.

---

## 🟡 Vấn đề 4: Semantic algorithm redesign thiếu benchmark baseline

### Hiện trạng

Architecture review chỉ ra semantic splitter có vấn đề:

- Percentile 80% với `>=` threshold tạo quá nhiều boundary
- Lexical Jaccard fallback nhạy với stopwords
- Window size 2 không cân xứng đầu/cuối
- Trailing small cluster không merge ngược

Plan đề xuất sửa thành "local maxima + minimum evidence + deterministic ties" nhưng **không có baseline performance số liệu**: không biết chunk count hiện tại, retrieval accuracy, semantic coherence score.

**Risk:** sửa algorithm mà không biết baseline → không biết có cải thiện hay không.

### Khuyến nghị

**Phase 0 bắt buộc:**

1. Chạy current chunker trên representative corpus (e.g., 10 docs pháp luật, 10 docs kỹ thuật).
2. Đo:
   - Chunk count distribution (p50, p95, max)
   - Semantic coherence (nếu có embedding): avg cosine sim giữa các câu trong chunk
   - Manual review: sample 50 chunks, đánh giá "có bị cắt giữa chủ đề không?"
3. Ghi baseline vào `docs/chunking_baseline_metrics.md`.

**Phase semantic-redesign bắt buộc:**

- Chạy lại metrics trên cùng corpus, so sánh với baseline.
- Chỉ merge vào main nếu: coherence tăng ≥ 10% HOẶC chunk count giảm ≥ 15% với coherence không giảm.

---

## 🟡 Vấn đề 5: Property-based tests đẹp nhưng ROI thấp cho context này

### Hiện trạng

Plans đề xuất dùng Hypothesis cho property-based tests (provenance coverage, reading order monotonic, token budget bounded).

**Thực tế:**

1. Property-based tests tốn effort viết + maintain generators.
2. RAG chunking có nhiều domain-specific edge cases (Vietnamese punctuation, Markdown tables, legal citations) → cần **concrete fixtures** hơn là random generators.
3. Khi bug xuất hiện, property test cho failure case rất general → khó reproduce.

### Khuyến nghị

Ưu tiên golden/regression tests hơn property tests:

```python
# Good: Concrete fixture
def test_vietnamese_abbreviation_provenance():
    """ThS., TS. không bị tách thành nhiều câu, provenance phải đúng element."""
    element = LayoutElement(
        id="e1",
        text="ThS. Nguyễn Văn A làm việc tại TP. Hồ Chí Minh.",
        type="paragraph",
        page_number=1,
    )
    chunks = chunker.chunk([element], document_id="doc1")
    assert len(chunks) == 1
    assert chunks[0].element_ids == ["e1"]
    assert "ThS. Nguyễn Văn A" in chunks[0].content
```

Nếu vẫn muốn property tests, chỉ dùng cho **contract invariants cơ bản**:

- `all(c.page_start <= c.page_end for c in chunks)`
- `all(c.token_count > 0 for c in chunks if c.indexable)`

Không dùng cho semantic logic (quá phức tạp để express as properties).

---

## ✅ Những điểm tốt cần giữ nguyên

1. **Provenance redesign (SpanRef + RowRef)** — đúng hướng, critical fix.
2. **Canonical reading order** — cần thiết cho production.
3. **Fail-fast validation** — đúng, không silent repair.
4. **Cross-page section context** — quan trọng cho legal/technical docs.
5. **Table header repetition** — logic đã đúng, giữ nguyên.

---

## Khuyến nghị tổng kết: kế hoạch 3-phase thực tế hơn

### Phase 1 (2 tuần) — Contract & Provenance ONLY

Mục tiêu: fix P0 provenance + reading order, không động semantic algorithm.

- SpanRef/RowRef contract
- Canonical sort (page + bbox + source_order)
- Derive element_ids/bboxes from provenance
- Cross-page sections
- Validation fail-fast
- Golden tests

**Exit:** Provenance 100% accurate, order deterministic, backward compatible.

### Phase 2 (2 tuần) — Token budget & Table improvements

Mục tiêu: token-aware chunking, không thay semantic boundary logic.

- TokenCounter protocol (embedding model tokenizer)
- Budget enforcement pre-embedding
- Table row packing theo tokens
- Oversize diagnostics
- Benchmark baseline metrics

**Exit:** Zero token overflow, table chunks có row provenance.

### Phase 3 (3-4 tuần) — Semantic algorithm v2

Mục tiêu: improve topic boundary detection.

- Offset-preserving sentence splitter
- Embedding validation + typed fallback
- Local maxima boundary selection
- Trailing cluster merge fix
- A/B test với baseline

**Exit:** Coherence tăng ≥ 10% hoặc chunk count giảm ≥ 15%.

---

## Kết luận

Plan hiện tại **kỹ thuật tốt nhưng phạm vi quá lớn**. Chia nhỏ thành 3 increments riêng biệt, mỗi increment có exit criteria đo được → deployment an toàn hơn, rollback dễ hơn, debug nhanh hơn.

**Recommendation:** thực hiện Phase 1 trước (contract + provenance), đợi ổn định 1-2 tuần production, rồi mới làm Phase 2 & 3.
