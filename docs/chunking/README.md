# Tài Liệu Kiến Trúc & Chiến Lược Chunking (Document Chunking)

Thư mục này tập hợp toàn bộ tài liệu kiến trúc, đặc tả kỹ thuật và phân tích chuyên sâu về hệ thống **Băm nhỏ tài liệu (Document Chunking)** trong hệ thống RAG Enterprise (`packages/rag-document-pipeline`).

---

## 📚 Danh Mục Tài Liệu

| Tài liệu | Mô tả trọng tâm | Phạm vi & Thành phần liên quan |
| :--- | :--- | :--- |
| 🧩 [**Kiến Trúc Chunking Lai & Luồng Toàn Trình**](./chunking_architecture.md)<br>`chunking_architecture.md` | - Mô hình Lai 2 tầng (Heading-Aware + Semantic Topic Shifts)<br>- Chiến lược Zero-RAM-Bloat & Staging MinIO/S3<br>- Quy chuẩn phân luồng Multimodal (Text / Table / Image) | `packages/rag-document-pipeline`<br>`apps/worker`<br>`packages/rag-core` |
| 📊 [**Chiến Lược Chunking Bảng Biểu**](./table_chunking_architecture.md)<br>`table_chunking_architecture.md` | - Bảo toàn cấu trúc 2 chiều (Structure-Preserving Table Chunking)<br>- Repeated Headers tự động cho sub-table chunks<br>- Oversized Row Splitting & Row-wise Key-Value template | `rag_document_pipeline.chunking.strategies.table`<br>`rag_document_pipeline.chunking.multimodal` |
| 🖼️ [**Kiến Trúc Xử Lý Hình Ảnh & Đa Phương Thức**](./image_processing_architecture.md)<br>`image_processing_architecture.md` | - Image Triage lọc ảnh rác / trang trí<br>- Dual-Engine OCR Router (Tesseract + VLM Fallback)<br>- Structured VLM Vision Analysis & Visual Citations (Presigned URL) | `rag_document_pipeline.chunking.strategies.image`<br>`rag_core.providers.ocr`<br>`apps/chat-api` |
| 🔍 [**Phân Tích Hiện Tượng Phân Mảnh Ngữ Cảnh**](./multimodal_context_fragmentation_analysis.md)<br>`multimodal_context_fragmentation_analysis.md` | - Phân tích bài toán Context Fragmentation (Semantic Decoupling)<br>- Đối chiếu Tutorial PoC (`langchain_multimodal.ipynb`) vs Production<br>- Vai trò của `section_path`, Reading Order và Caption Binding | `rag_document_pipeline.normalizers.layout`<br>`rag_contracts.chunks`<br>`database_design.md` |

---

## 🛠️ Bản Đồ Mã Nguồn Triển Khai (Source Code Map)

Hệ thống chunking được triển khai theo cấu trúc module độc lập trong [`packages/rag-document-pipeline/src/rag_document_pipeline/chunking`](../../packages/rag-document-pipeline/src/rag_document_pipeline/chunking):

```
packages/rag-document-pipeline/src/rag_document_pipeline/chunking/
├── base.py                   # Protocol BaseChunker & Interface chung
├── multimodal.py             # MultimodalChunker (Tầng 1 - Router điều phối vĩ mô)
└── strategies/
    ├── __init__.py
    ├── text.py               # TextChunker (Heading-Aware + Semantic sliding window)
    ├── table.py              # TableChunker (Repeated Header, Oversized Row Split, Key-Value text)
    └── image.py              # ImageChunker (Caption, OCR, Visual Description & Indexable filter)
```

---

## 🔗 Liên Kết Tham Chiếu Ngoài
- 📄 [Kiến Trúc & Hướng Dẫn Document Pipeline](../document_pipeline.md): Điều phối toàn trình Parse → Normalize → Chunk → Validate.
- 🏗️ [Master Architecture Design](../architecture.md): Tổng thể kiến trúc hệ thống RAG.
- 🗄️ [Thiết Kế Cơ Sở Dữ Liệu](../database_design.md): Schema bảng `chunks`, pgvector HNSW index và TSVector FTS.
