# Tài liệu Yêu cầu Hệ thống RAG (Software Requirements Specification - SRS)

> **Dự án:** FastAPI RAG Backend with PostgreSQL pgvector  
> **Phiên bản tài liệu:** 1.0  
> **Ngày tạo:** 11/08/2026  
> **Trạng thái:** Được phê duyệt triển khai  
> **Tài liệu tham chiếu:** [RAG_Architecture_Design.md](file:///c:/Users/Admin/Documents/Project/ragflow-api/docs/RAG_Architecture_Design.md)

---

## 1. Tóm tắt & Mục tiêu Sản phẩm

Hệ thống **ragflow-api** là một Backend REST API được xây dựng theo kiến trúc **modular monolith** nhằm cung cấp giải pháp **Retrieval-Augmented Generation (RAG)** phục vụ quản lý, truy tìm văn bản và hỏi đáp thông minh dựa trên tri thức doanh nghiệp.

### 1.1 Mục tiêu chính
- **Nạp và xử lý tài liệu đa định dạng:** Hỗ trợ PDF, DOCX, TXT, Markdown, JSON, CSV với khả năng làm sạch văn bản và phân đoạn (chunking) linh hoạt.
- **Lưu trữ & Truy hồi hiệu năng cao:** Kết hợp PostgreSQL và pgvector để quản lý metadata, văn bản gốc, full-text search index (GIN) và vector embeddings index (HNSW).
- **Truy hồi lai (Hybrid Search) & Mở rộng ngữ cảnh:** Kết hợp Vector Search và Full-text Search thông qua Reciprocal Rank Fusion (RRF), bổ sung Neighbor Expansion và Context Merge để giữ nguyên ngữ cảnh các bảng biểu, đoạn văn bị cắt ranh giới.
- **Hỏi đáp RAG chính xác:** Tự động tạo prompt kèm trích dẫn nguồn `[Source #n]` chuẩn xác và sinh câu trả lời bằng các mô hình LLM tiên tiến (OpenAI, Gemini) hoặc Mock Provider cho môi trường kiểm thử.
- **Tích hợp mở rộng:** Cung cấp API chuẩn REST, giao thức Model Context Protocol (MCP) Server cho các AI Agent bên ngoài và LangGraph Agent integration.

---

## 2. Phạm vi Hệ thống (Scope & Out of Scope)

### 2.1 Trong phạm vi (In Scope)
- RESTful API endpoints cho quản lý tài liệu, tìm kiếm và hỏi đáp RAG.
- Quy trình Ingestion đồng bộ (với giao diện chuẩn bị cho Async Workers).
- Vector Storage & Full-Text Search trong PostgreSQL qua pgvector extension.
- Tích hợp LangChain Adapters cho Embedding và LLM Generation (OpenAI, Gemini, Mock).
- Cơ chế mở rộng chunk lân cận (Neighbor Expansion) và gộp chunk liên tiếp (Context Merge).
- Quản lý Migration cơ sở dữ liệu tự động với Alembic.
- Giao thức MCP (Model Context Protocol) Server và MCP Tools.
- Bộ kiểm thử đơn vị (Unit Test) và đóng gói môi trường Docker Compose.

### 2.2 Ngoài phạm vi hiện tại (Out of Scope / Backlog)
- Giao diện người dùng (Frontend Web / Mobile App).
- Giao diện quản trị hệ thống đa người dùng (Multi-tenant Admin Portal).
- Nhận dạng chữ viết / hình ảnh qua OCR cho file PDF dạng scan.
- Tự động quét virus / mã độc cho file upload (Antivirus scanning).
- Hàng chờ xử lý bất đồng bộ thực thụ (Celery / Arq Worker queue - hiện tại mới có stub).
- Đánh giá chất lượng RAG tự động trên môi trường Production (RAG Triad / Ragas metrics evaluation - hiện tại ở mức backlog).
- Driver kết nối Object Storage bên ngoài (AWS S3, MinIO - hiện lưu trữ DB direct).

---

## 3. Yêu cầu Chức năng (Functional Requirements - FR)

### 3.1 Nạp & Xử lý Tài liệu (Document Ingestion)
- **`FR-DOC-01` Upload File:** Hệ thống phải cho phép client nạp file qua API `POST /api/v1/documents/upload`. Hỗ trợ các định dạng `.pdf`, `.docx`, `.txt`, `.md`, `.json`, `.csv` với dung lượng tối đa 20MB per file.
- **`FR-DOC-02` Ingest Text trực tiếp:** Hệ thống phải cung cấp API `POST /api/v1/documents/ingest-text` để nạp văn bản thô trực tiếp mà không cần upload file.
- **`FR-DOC-03` Làm sạch Văn bản (Text Sanitization):** Hệ thống phải tự động loại bỏ ký tự NULL (`\x00`), các ký tự điều khiển ASCII/Unicode không hợp lệ trước khi đưa vào pipeline.
- **`FR-DOC-04` Kiểm tra PDF Text Layer:** Với file PDF, hệ thống phải xác thực xem PDF có lớp text hay không. Nếu PDF là file ảnh scan (không chứa text), hệ thống từ chối nạp và trả về lỗi `422 OCR required`.
- **`FR-DOC-05` Phân đoạn Văn bản (Chunking):** 
  - Hệ thống phải chia nhỏ văn bản bằng `RecursiveCharacterTextSplitter`.
  - Cho phép client tùy chỉnh `chunk_size` (mặc định 1.000) và `chunk_overlap` (mặc định 200).
  - Phải kiểm tra ràng buộc `chunk_overlap < chunk_size`, nếu vi phạm trả lỗi `422 Unprocessable Entity`.
- **`FR-DOC-06` Quản lý Tài liệu:**
  - Hệ thống cung cấp API `GET /api/v1/documents` để truy vấn danh sách tài liệu.
  - Hệ thống cung cấp API `DELETE /api/v1/documents/{id}` để xóa tài liệu và toàn bộ các chunk liên quan.

### 3.2 Dịch vụ Embedding (Embedding Service)
- **`FR-EMB-01` Đa Provider:** Hệ thống phải hỗ trợ tạo embedding 1.536 chiều qua các provider: OpenAI (`text-embedding-3-small`), Gemini (`text-embedding-004`) và Mock Provider.
- **`FR-EMB-02` Lọc và Batching Chunk:** Hệ thống phải tự động loại bỏ các chunk rỗng trước khi gửi đến Embedding Provider và đảm bảo duy trì chính xác thứ tự của vector kết quả tương ứng với chunk.
- **`FR-EMB-03` Xử lý Rate Limit & Fail-fast:** Hệ thống phải triển khai cơ chế retry với exponential backoff khi gặp lỗi `422/429 (Rate Limit)` từ provider. Nếu thiếu API Key cấu hình cho provider thật, hệ thống phải fail-fast và báo lỗi thay vì âm thầm dùng Mock.

### 3.3 Lưu trữ & Cơ sở dữ liệu (Storage & Vector Database)
- **`FR-VEC-01` Quản lý Metadata & Content:** Hệ thống phải lưu trữ metadata tài liệu (tên file, định dạng, kích thước, số lượng chunk) trong bảng `documents` và nội dung chunk trong bảng `document_chunks`.
- **`FR-VEC-02` Vector Indexing (HNSW):** Hệ thống phải tạo chỉ mục HNSW với tham số `m=16`, `ef_construction=64` trên cột vector bằng toán tử `vector_cosine_ops` để tối ưu tốc độ tìm kiếm tương đồng.
- **`FR-VEC-03` Full-text Search Indexing (GIN):** Hệ thống phải khởi tạo chỉ mục GIN trên cột `tsvector` của bảng `document_chunks` cấu hình ngôn ngữ `simple` phục vụ truy tìm từ khóa.
- **`FR-VEC-04` Audit Trail & Soft Delete:** Tất cả các bảng dữ liệu phải kế thừa `AuditMixin` chứa các cột `created_at`, `updated_at`, `created_by`, `updated_by`, `deleted_at`. Hệ thống phải lọc `deleted_at IS NULL` trong mọi truy vấn đọc.
- **`FR-VEC-05` Schema Migration:** Mọi thay đổi cấu trúc bảng cơ sở dữ liệu phải được quản lý tập trung thông qua các file Alembic revision (`migrations/versions/`).

### 3.4 Truy hồi & Tìm kiếm (Search & Retrieval)
- **`FR-RET-01` Vector Search:** API `POST /api/v1/retrieval/search` với `search_type="vector"` phải tìm kiếm `Top-K` chunk có khoảng cách Cosine nhỏ nhất so với query vector.
- **`FR-RET-02` Hybrid Search (RRF Fusion):** Với `search_type="hybrid"`, hệ thống phải thực hiện đồng thời Vector Search và Full-text Search (`ts_rank_cd`), sau đó hợp nhất danh sách bằng thuật toán Reciprocal Rank Fusion (RRF) với hằng số `k=60`:
  $$\text{RRF Score} = \sum \frac{1}{60 + \text{rank}}$$
- **`FR-RET-03` Mở rộng Chunk Lân cận (Neighbor Expansion):** Sau khi lấy được `Top-K` seed chunks, hệ thống phải tự động truy vấn thêm các chunk lân cận thuộc phạm vi `[seed - N, seed + N]` (với `N = RAG_NEIGHBOR_WINDOW`) cùng thuộc một `document_id`.
- **`FR-RET-04` Gộp Context & Loại Overlap (Context Merging):** Hệ thống phải sắp xếp các chunk mở rộng theo `document_rank -> document_id -> chunk_index`, tiến hành gộp các chunk liên tiếp và loại bỏ phần trùng lặp văn bản tại ranh giới cắt.
- **`FR-RET-05` Bộ lọc theo Tài liệu:** Hệ thống phải hỗ trợ tham số `document_id` tùy chọn trong API tìm kiếm để giới hạn phạm vi truy vấn trong 1 tài liệu cụ thể.

### 3.5 Sinh Phản hồi RAG & Citations (Generation & Chat)
- **`FR-GEN-01` Xây dựng Prompt RAG:** Hệ thống phải tự động ráp ngữ cảnh từ các chunk đã được truy hồi và gộp thành System Message và Human Message có cấu trúc phân định rõ ràng.
- **`FR-GEN-02` Đánh số Trích dẫn (Citations):** Mỗi đoạn ngữ cảnh trong Prompt gửi tới LLM phải được đánh số trích dẫn theo định dạng `[Source #n] (Doc ID: ..., Chunk Indexes: ...)`.
- **`FR-GEN-03` Tích hợp LLM Provider:** Hệ thống phải hỗ trợ sinh văn bản thông qua OpenAI (`gpt-4o-mini`), Gemini (`gemini-1.5-flash`) hoặc Mock LLM Provider qua adapter LangChain.
- **`FR-GEN-04` Cấu trúc Phản hồi RAG Chat:** API `POST /api/v1/chat/query` phải trả về đối tượng JSON chứa câu hỏi gốc (`query`), câu trả lời (`answer`) và danh sách ngữ cảnh được trích xuất (`retrieved_contexts`).

### 3.6 REST API & Giao thức tích hợp
- **`FR-API-01` Schema Phản hồi Chuẩn:** Mọi phản hồi REST API phải tuân theo định dạng chuẩn `ApiResponse` gồm `success: bool`, `data: Any`, `error: Optional[ErrorDetails]`.
- **`FR-API-02` Kiểm tra Trạng thái (Health Check):** Endpoint `GET /api/v1/health` phải kiểm tra tính sẵn sàng của kết nối PostgreSQL, sự tồn tại của pgvector extension và phiên bản Alembic migration.
- **`FR-API-03` MCP Server Integration:** Hệ thống cung cấp MCP Server (`app/mcp/server.py`) hỗ trợ hai MCP Tools: `search_documents` và `get_document` cho phép tích hợp trực tiếp với Claude Desktop hoặc các Cursor/VSCode AI Extensions.

---

## 4. Yêu cầu Phi chức năng (Non-Functional Requirements - NFR)

### 4.1 Hiệu năng & Độ trễ (Performance & Latency)
- **`NFR-PERF-01` Thời gian phản hồi Tìm kiếm (Search Latency):** Thời gian thực thi Vector Search và Hybrid Search trên tập dữ liệu dưới 100.000 chunks phải đạt $\le 200\text{ms}$ (chưa tính thời gian gọi Embedding API).
- **`NFR-PERF-02` Tối ưu hóa Vector Index:** Chỉ mục HNSW phải duy trì hiệu năng truy vấn ổn định ngay cả khi dung lượng cơ sở dữ liệu tăng trưởng.
- **`NFR-PERF-03` Xử lý Lô (Bulk Insertion):** Lưu trữ chunk văn bản phải thực hiện theo cơ chế Bulk Insert / Batch Flush để giảm số lượng round-trip truy vấn DB trong quá trình Ingestion.

### 4.2 An ninh & Bảo mật (Security & Authorization)
- **`NFR-SEC-01` Xác thực Middleware (Auth Backlog P0):** Hệ thống phải tích hợp JWT / OAuth2 Bearer token middleware để bảo vệ các endpoints REST API.
- **`NFR-SEC-02` Phân quyền đa người dùng (Multi-tenant RBAC Backlog P0):** Truy vấn tài liệu phải được kiểm soát truy cập theo `tenant_id` hoặc `created_by` nhằm ngăn chặn rò rỉ dữ liệu giữa các người dùng.
- **`NFR-SEC-03` Giới hạn Tần suất (Rate Limiting Backlog P0):** Áp dụng middleware Rate Limiting (ví dụ: Slowapi hoặc Redis Rate Limiter) để ngăn ngừa các cuộc tấn công DDoS / Brute force vào API upload và chat.
- **`NFR-SEC-04` Bảo mật API Key:** Các API key nhạy cảm của OpenAI / Gemini không được lưu trực tiếp trong mã nguồn hay cơ sở dữ liệu mà phải nạp từ môi trường qua `.env` / Pydantic Settings.

### 4.3 Độ tin cậy & Tính Toàn vẹn Dữ liệu (Reliability & Transaction Integrity)
- **`NFR-REL-01` Atomicity trong Ingestion:** Toàn bộ quá trình tạo `Document` và lưu danh sách `DocumentChunk` phải nằm trong **1 DB Transaction duy nhất**. Nếu quá trình parse, tạo embedding hoặc lưu DB bị lỗi, hệ thống phải `ROLLBACK` hoàn toàn, không để lại dữ liệu rác.
- **`NFR-REL-02` Isolation & Fail-Fast:** Khởi tạo ứng dụng phải kiểm tra trước kết nối cơ sở dữ liệu và cấu hình bắt buộc. Thiếu API Key bắt buộc phải dừng ứng dụng ngay lập tức (`Fail-fast`).
- **`NFR-REL-03` Sao lưu & Khôi phục (Backup & Recovery Backlog P0):** Quy trình sao lưu định kỳ cơ sở dữ liệu PostgreSQL kèm pgvector data và diễn tập khôi phục (Disaster Recovery).

### 4.4 Khả năng Bảo trì & Mở rộng (Maintainability & Scalability)
- **`NFR-MAINT-01` Kiến trúc Phân lớp (Modular Monolith):** Mã nguồn phân định rõ ràng giữa các lớp API, Application, Domain, Service/Adapter và Infrastructure. Các dependency phải đi theo chiều một hướng.
- **`NFR-MAINT-02` Cấu trúc Độc lập Module:** Các module mở rộng như `agents`, `mcp`, `workers` có thể phát triển hoặc tách ra thành Microservices riêng biệt mà không ảnh hưởng tới core API.
- **`NFR-MAINT-03` Quản lý Migration:** Tất cả thay đổi Database Schema phải được kiểm soát phiên bản qua Alembic, không tự động gọi `create_all()`.

### 4.5 Observability & Logging
- **`NFR-OBS-01` Structured Logging:** Log ứng dụng phải ghi dưới dạng cấu trúc JSON bao gồm `timestamp`, `level`, `module`, `trace_id`, `message` hỗ trợ thu thập bởi Logstash/Fluentd/Datadog.
- **`NFR-OBS-02` OpenTelemetry Tracing (Backlog P1):** Chuẩn bị sẵn khả năng gắn tracing context qua luồng Ingestion, Retrieval và LLM Call.
- **`NFR-OBS-03` Prometheus Metrics (Backlog P1):** Đo lường số lượng HTTP Requests, độ trễ từng endpoint, số lượng embedding tokens đã tiêu thụ và thời gian phản hồi từ LLM Providers.

---

## 5. Ràng buộc Hệ thống & Phụ thuộc (Constraints & Dependencies)

### 5.1 Ràng buộc Kỹ thuật & Công nghệ
- **Ngôn ngữ & Framework:** Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2.0 (Async/Sync hybrid).
- **Cơ sở dữ liệu:** PostgreSQL 16+ cài đặt sẵn extension `pgvector` (phiên bản $\ge 0.5.0$).
- **Adapter AI Framework:** LangChain / LangChain-Community / LangChain-Core cho lớp Adapter.
- **Đóng gói Môi trường:** Docker & Docker Compose (v2.x+).

### 5.2 Phụ thuộc Bên ngoài
- **OpenAI API:** Mô hình `text-embedding-3-small` (dimension 1536) và `gpt-4o-mini`.
- **Google Gemini API:** Mô hình `text-embedding-004` và `gemini-1.5-flash`.

---

## 6. Tiêu chí Nghiệm thu Hệ thống (Acceptance Criteria)

1. **DB Migration:** Chạy thành công `alembic upgrade head`, khởi tạo đầy đủ các extension `vector`, bảng `documents`, `document_chunks` và các index HNSW, GIN, B-Tree.
2. **Containerization:** Lệnh `docker compose up --build` khởi động container API và PostgreSQL về trạng thái `healthy`.
3. **Input Validation:** Nạp file không đúng định dạng, vượt quá 20MB hoặc cấu hình `chunk_overlap >= chunk_size` trả về đúng các mã lỗi HTTP `415`, `413`, `422`.
4. **Transaction Safety:** Lỗi sinh embedding giữa chừng không tạo tài liệu mồ côi hay chunk dở dang trong database (xác nhận ROLLBACK thành công).
5. **Retrieval & Filtering:** Kết quả truy hồi `search_type="hybrid"` và `search_type="vector"` tôn trọng đúng bộ lọc `document_id`.
6. **RAG Chat Response:** API chat phản hồi câu trả lời hợp lệ kèm danh sách `retrieved_contexts` có đầy đủ trích dẫn `[Source #n]`.
7. **Test Coverage:** Bộ kiểm thử đơn vị (`pytest tests/unit/`) đạt 100% tỷ lệ pass (31/31 unit test cases thành công).
