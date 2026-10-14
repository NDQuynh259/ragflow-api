# Tổ chức lại package `rag_document_pipeline.chunking`

## Context

Layout hiện tại (đã kiểm chứng):

```
chunking/
├── __init__.py          # facade: re-export from .core, .multimodal, .strategies
├── multimodal.py        # MultimodalChunker (router + re-index chunk.index)
├── core/
│   ├── __init__.py      # barrel: Chunker, section utils, metrics, image helpers
│   ├── base.py          # Chunker Protocol
│   ├── section.py       # propagate_sections, group_by_section
│   ├── utils.py         # estimate_tokens, cosine_distance, jaccard_distance
│   └── image.py         # helper thuần: triage, extraction, text proxy, chunk builder + aliases
└── strategies/
    ├── __init__.py      # ImageChunker, TableChunker, TextChunker
    ├── image.py         # ImageChunker (orchestration 6 bước)
    ├── table.py         # TableChunker + private/static helpers
    └── text.py          # TextChunker + private/static helpers
```

Điểm lệch cần xử lý:

1. Helper của image nằm ở `core/image.py`, nhưng helper của table/text vẫn là private/static method bên trong `strategies/table.py`, `strategies/text.py`.
2. Style import lẫn lộn: `chunking/__init__.py` dùng relative (`from .core import ...`), trong khi `multimodal.py`, `strategies/*.py`, `core/image.py` dùng absolute (`rag_document_pipeline.chunking.core...`).
3. Facade `chunking/__init__.py` re-export cả metric helper (`cosine_distance`, `jaccard_distance`, `estimate_tokens`, `group_by_section`, `propagate_sections`) dù không có consumer nào import từ facade (chỉ `pipeline.py` và tests import theo đường submodule).
4. Alias tương thích (`image_source`, `image_text_proxy`, `make_image_chunk`) chỉ có một nơi định nghĩa nhưng được export ở 2 tầng.
5. Map mã nguồn trong docs đã lệch so với layout thật.

## Quyết định đã chốt

- **Quy tắc helper (cách A)**: `core/` giữ hạ tầng dùng chung (`Chunker`, section, metrics) cộng với layer helper thuần của image (hiện được test trực tiếp trong `tests/test_image_triage.py`). Helper chỉ một strategy dùng vẫn ở lại `strategies/<modality>.py` dưới dạng private/static method. Không di chuyển helper của table/text.
- **Hợp đồng `MultimodalChunker.__init__(**_)`**: chỉ ghi nhận, KHÔNG sửa trong đợt này. Hành vi hiện hữu: `DocumentPipeline.hybrid_semantic(max_chunk_size=1500)` rơi vào `**_` và bị bỏ qua, `TextChunker` vẫn nhận `chunk_size` mặc định 1200. Giữ nguyên để không đổi output chunk.
- Giữ mọi đường import đang được dùng: `chunking.multimodal`, `chunking.strategies.{image,table,text}`, `chunking.core`, `chunking.core.image`, và facade `chunking`. Không rename module.
- Giữ nguyên các alias tương thích, chỉ khai báo một nơi duy nhất (`core/image.py`).

## Tasks

1. **Khai báo quy tắc trong docstring** (không đổi logic):
   - `chunking/__init__.py`: facade là public surface cho app code.
   - `chunking/core/__init__.py`: hạ tầng dùng chung + helper thuần, không chứa orchestration.
   - `chunking/strategies/*.py`: orchestration theo modality; helper riêng của chính nó nằm tại chỗ.

2. **Thống nhất style import nội bộ**: chuyển sang relative import trong toàn bộ package (`from .core import ...`, `from .core.image import ...`, `from .strategies import ...`), giữ absolute cho cross-package (`rag_contracts`, `rag_document_pipeline.models`). Áp dụng cho `multimodal.py`, `strategies/image.py`, `strategies/table.py`, `strategies/text.py`, `core/image.py`.

3. **Thu gọn facade `chunking/__init__.py`**: export `Chunker`, `MultimodalChunker`, `ImageChunker`, `TableChunker`, `TextChunker`. Bỏ metric/section helper khỏi `__all__` của facade; chúng vẫn import được qua `rag_document_pipeline.chunking.core` (cách `strategies/table.py`, `strategies/text.py`, `multimodal.py` đang dùng). Trước khi bỏ, grep `from rag_document_pipeline.chunking import` để xác nhận không có consumer nào lấy metric helper từ facade; nếu có thì giữ lại tên đó.

4. **Chốt một nơi định nghĩa alias**: giữ alias tại `core/image.py`; bảo đảm `strategies/image.py` chỉ re-export (đã có trong `__all__`), không tạo alias thứ hai.

5. **Cập nhật map trong docs cho khớp layout thật** (chỉ đổi đường dẫn, không viết lại nội dung):
   - `docs/chunking/README.md` (khối cây thư mục, dòng ~22-31): thêm `core/` và `strategies/`.
   - `docs/chunking/chunking_architecture.md`: cây thư mục ở mục `Cấu Trúc Gói Mã Nguồn` (dòng ~84-93) và bảng `Danh Mục Mã Nguồn Triển Khai` (dòng ~639-648) — bổ sung `core/base.py`, `core/section.py`, `core/utils.py`, `core/image.py`, `strategies/*.py` thay vì dạng phẳng `chunking/base.py`.

## Boundaries

- Không đụng `MultimodalChunker.__init__`, không đụng thuật toán của `TextChunker`/`TableChunker`.
- Không sửa test; chỉ được sửa test nếu test import một path bị đổi (dự kiến không đổi path nào).
- Không đổi shape của `DocumentChunk`/metadata keys (`ocr_attempted`, `has_ocr`, `has_vision`, `triage_skipped`, `index_reason`, `searchable_text`).

## Failure modes cần chú ý

- Relative import trong `core/image.py` phải trỏ đúng `.utils`; circular import chỉ một chiều: `strategies/* -> core/*`, không chiều ngược lại.
- `pipeline.py` import `Chunker` từ `rag_document_pipeline.chunking.core` — giữ nguyên hoạt động sau khi barrel `core/__init__.py` được sắp xếp lại.
- Alias vẫn phải resolve được từ cả `chunking.strategies.image` lẫn `chunking.core.image`.
- Bỏ tên khỏi `__all__` của facade là thay đổi surface: nếu phát sinh consumer trong `apps/`, giữ lại tên đó thay vì ép migration.

## Validation

1. `uv run pytest packages/rag-document-pipeline/tests -q` → kỳ vọng 38 passed.
2. `uv run ruff check packages/rag-document-pipeline` và `uv run ruff format --check packages/rag-document-pipeline` cho các file đã chạm.
3. `uv run poe typecheck` → không thêm lỗi mới (baseline: 5 lỗi có sẵn ở `apps/scheduler` và `rag-core/providers/embeddings/gemini.py`).
4. Smoke import cả hai kiểu:
   - `uv run python -c "from rag_document_pipeline.chunking import MultimodalChunker, ImageChunker, Chunker"`
   - `uv run python -c "from rag_document_pipeline.chunking.multimodal import MultimodalChunker; from rag_document_pipeline.chunking.strategies.image import ImageChunker, safe_extract_text, make_image_chunk; from rag_document_pipeline.chunking.core import image_metadata"`
5. So sánh nhanh một lần chạy pipeline trên `output/` sample: số chunk, `kind`, và metadata keys của figure chunk không đổi so với trước refactor.

## Out of scope

- Sửa `**_` và hợp đồng `max_chunk_size` của `MultimodalChunker`.
- Viết lại nội dung prose trong `docs/chunking/*.md` (chỉ cập nhật đường dẫn module).
- Tách thêm module hoặc gộp module cho text/table.
