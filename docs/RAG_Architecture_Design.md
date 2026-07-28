# Thiết kế kiến trúc hệ thống RAG

> **Dự án:** FastAPI RAG Backend with PostgreSQL pgvector  
> **Phiên bản tài liệu:** 1.1  
> **Ngày cập nhật:** 28/07/2026  
> **Trạng thái:** Đồng bộ với mã nguồn và bộ kiểm thử hiện tại

## Tóm tắt

Hệ thống được tổ chức theo kiến trúc **modular monolith**, phù hợp cho MVP và
môi trường thử nghiệm. FastAPI cung cấp REST API; PostgreSQL và pgvector đảm
nhiệm lưu trữ metadata, nội dung, embedding và truy hồi; OpenAI, Gemini hoặc
mock provider cung cấp embedding và khả năng sinh câu trả lời.

Các lỗi về cấu hình database, validation, transaction ingestion, hybrid search,
index truy vấn, provider và Docker đã được xử lý. Schema được quản lý bằng
Alembic migration. Authentication và background worker vẫn là backlog trước
khi triển khai production.

## 1. Mục tiêu và phạm vi

Hệ thống hỗ trợ:

- Nạp tài liệu PDF, DOCX, TXT, Markdown, JSON và CSV.
- Chia văn bản thành các đoạn chồng lấn.
- Tạo embedding 1.536 chiều bằng OpenAI, Gemini hoặc mock provider.
- Lưu nội dung và embedding trong PostgreSQL/pgvector.
- Truy hồi bằng vector search hoặc hybrid search.
- Tạo prompt có context và citation `[Source #n]`.
- Sinh phản hồi bằng OpenAI, Gemini hoặc mock LLM.
- Cung cấp REST API và triển khai cục bộ bằng Docker Compose.

### Ngoài phạm vi hiện tại

- Frontend.
- Quản lý người dùng và phân quyền theo tenant.
- OCR tài liệu scan.
- Antivirus scanning.
- Reranker chuyên dụng.
- Đánh giá tự động chất lượng câu trả lời.
- Lưu trữ file gốc trong object storage.

## 2. Bối cảnh hệ thống

```mermaid
flowchart LR
    Client[Client / Frontend]
    API[FastAPI REST API<br/>/api/v1]
    DB[(PostgreSQL 16<br/>pgvector)]
    AI[AI Providers<br/>OpenAI / Gemini / Mock]

    Client -->|HTTPS / JSON| API
    API -->|SQLAlchemy / psycopg| DB
    API -->|Embedding và Generation API| AI
```

FastAPI là biên giao tiếp duy nhất của hệ thống. PostgreSQL lưu metadata tài
liệu, nội dung chunk, full-text document và vector embedding. Các nhà cung cấp
AI chỉ được truy cập qua lớp adapter tương ứng.

## 3. Kiến trúc logic

```mermaid
flowchart TB
    Main[main.py<br/>Lifespan và CORS]
    Schemas[API Schemas<br/>Pydantic validation]
    Routes[API Routes<br/>Use-case orchestration]

    Parser[Document Parser]
    Chunker[Text Chunker]
    Embedding[Embedding Service]
    Store[Vector Store Service]
    Prompt[Prompt Builder]
    LLM[LLM Service]

    Database[SQLAlchemy]
    Migration[Alembic Migrations]
    PG[(PostgreSQL + pgvector)]

    Main --> Routes
    Schemas --> Routes
    Routes --> Parser
    Routes --> Chunker
    Routes --> Embedding
    Routes --> Store
    Routes --> Prompt
    Routes --> LLM
    Store --> Database
    Database --> PG
    Migration --> PG
```

### Trách nhiệm thành phần

| Thành phần | Trách nhiệm | Tệp chính |
|---|---|---|
| Bootstrap | Khởi tạo FastAPI, lifespan và CORS | `main.py` |
| Configuration | Đọc và kiểm tra biến môi trường | `app/config.py` |
| API schemas | Request/response contract và validation | `app/api/schemas.py` |
| API routes | Điều phối ingestion, retrieval và chat | `app/api/routes.py` |
| Parser | Trích xuất nội dung từ các loại tài liệu | `app/services/parser.py` |
| Chunker | Chia văn bản theo cửa sổ ký tự | `app/services/chunker.py` |
| Embedding | Adapter OpenAI, Gemini và mock | `app/services/embedding.py` |
| Vector store | Lưu chunk, vector search và hybrid search | `app/services/vector_store.py` |
| Prompt builder | Tạo prompt có context và citation | `app/services/prompt_builder.py` |
| LLM | Adapter OpenAI, Gemini và mock | `app/services/llm.py` |
| Persistence | Session, schema, pgvector và index | `app/database.py`, `app/models.py` |
| Migration | Quản lý phiên bản và thay đổi database schema | `migrations/`, `alembic.ini` |

Routes hiện đóng vai trò application orchestrator. Khi số lượng use case tăng,
nên tách logic này thành `IngestionService` và `QueryService` để API chỉ đảm
nhiệm chuyển đổi giao thức.

## 4. Luồng ingestion

```mermaid
sequenceDiagram
    participant C as Client
    participant A as FastAPI
    participant P as Parser
    participant CH as Chunker
    participant E as Embedding Provider
    participant DB as PostgreSQL

    C->>A: Upload file hoặc raw text
    A->>A: Validate loại file, kích thước và chunk window
    A->>P: Parse file
    P-->>A: Raw text
    A->>CH: Split text
    CH-->>A: Chunks

    loop Từng chunk
        A->>E: Create embedding
        E-->>A: Vector
    end

    A->>DB: Begin transaction
    A->>DB: Insert Document
    A->>DB: Insert DocumentChunk[]

    alt Thành công
        A->>DB: Commit
        A-->>C: 201 DocumentResponse
    else Có lỗi
        A->>DB: Rollback
        A-->>C: Error response
    end
```

### Quy tắc ingestion

1. Kiểm tra extension, giới hạn file mặc định 20 MB và tham số chunk.
2. `chunk_size` phải lớn hơn `0`.
3. `chunk_overlap` không được âm và phải nhỏ hơn `chunk_size`.
4. Parse và tạo embedding trước khi ghi dữ liệu.
5. `Document` và toàn bộ `DocumentChunk` được ghi trong cùng một transaction.
6. Provider đã chọn nhưng thiếu API key phải báo lỗi, không fallback sang mock.
7. NUL và control characters được loại bỏ trước khi chunk/lưu.
8. PDF có text layer lỗi bị từ chối với hướng dẫn chạy OCR.
9. Chunk được flush theo batch để tránh câu lệnh insert quá lớn.

### Giới hạn

Embedding hiện vẫn chạy tuần tự trong request worker. Với tài liệu lớn, nên
chuyển ingestion sang background worker và sử dụng batch embedding để tránh
timeout.

## 5. Luồng retrieval và generation

```mermaid
flowchart TB
    Q[User question]
    QE[Query embedding]
    VS[Vector Search<br/>Cosine + HNSW]
    FTS[Full-text Search<br/>simple + GIN]
    RRF[Reciprocal Rank Fusion<br/>k = 60]
    Context[Top-K context chunks]
    Prompt[Prompt + Source citations]
    LLM[OpenAI / Gemini / Mock]
    Answer[Answer + retrieved_contexts]

    Q --> QE
    QE --> VS
    Q --> FTS
    VS --> RRF
    FTS --> RRF
    RRF --> Context
    Context --> Prompt
    Q --> Prompt
    Prompt --> LLM
    LLM --> Answer
```

### Vector search

- Dùng toán tử cosine distance `<=>` của pgvector.
- Query vector được cast rõ ràng sang kiểu `vector`.
- Có thể lọc theo `document_id`.
- HNSW index dùng `vector_cosine_ops`.

### Hybrid search

Hybrid search kết hợp:

1. Xếp hạng từ vector search.
2. PostgreSQL full-text search bằng `ts_rank_cd`.
3. Reciprocal Rank Fusion để hợp nhất hai bảng xếp hạng.

Full-text search sử dụng cấu hình `simple`, phù hợp với nội dung tiếng Việt hơn
cấu hình `english` vì không áp dụng English stemming.

> **Lưu ý:** `ts_rank_cd` không phải BM25. Nếu hệ thống yêu cầu BM25 thực sự,
> cần bổ sung PostgreSQL extension hoặc search engine chuyên dụng và đánh giá
> lại chất lượng retrieval.

## 6. Thiết kế dữ liệu

```mermaid
erDiagram
    DOCUMENT ||--o{ DOCUMENT_CHUNK : contains

    DOCUMENT {
        string id PK
        string filename
        string file_type
        integer file_size
        integer chunk_count
        datetime created_at
    }

    DOCUMENT_CHUNK {
        string id PK
        string document_id FK
        integer chunk_index
        text content
        json metadata_json
        vector embedding
        datetime created_at
    }
```

### Quan hệ và ràng buộc

- Một `Document` có nhiều `DocumentChunk`.
- `DocumentChunk.document_id` tham chiếu `Document.id`.
- Khi xóa document, các chunk liên quan được xóa cascade.
- Embedding không nullable trong schema mới.
- `metadata_json` dùng `default=dict` để tránh chia sẻ mutable default.
- Kích thước vector mặc định là `1536`.

### Index

| Index | Loại | Mục đích |
|---|---|---|
| `ix_document_chunks_document_id` | B-tree | Lọc chunk theo tài liệu |
| `ix_document_chunks_embedding_hnsw` | HNSW cosine | Approximate nearest-neighbor search |
| `ix_document_chunks_fts_simple` | GIN expression | Full-text retrieval với cấu hình `simple` |

Schema hiện ở Alembic head `20260728_0002`. Revision `20260728_0001` tạo
extension, bảng và index ban đầu; revision `20260728_0002` bảo đảm GIN
full-text index tồn tại. Application startup chỉ kiểm tra trạng thái database
và không tự ý thay đổi schema.

### Tính tương thích embedding

Không nên trộn vector từ nhiều model trong cùng một collection. Khi thay đổi
provider hoặc embedding model, cần:

- Re-index toàn bộ tài liệu; hoặc
- Bổ sung khái niệm collection cùng trường `embedding_model`.

## 7. Thiết kế API

| Method | Endpoint | Mục đích |
|---|---|---|
| `GET` | `/` | Thông tin ứng dụng |
| `GET` | `/api/v1/health` | Kiểm tra database và pgvector |
| `POST` | `/api/v1/documents/upload` | Upload và index tài liệu |
| `POST` | `/api/v1/documents/ingest-text` | Index raw text |
| `GET` | `/api/v1/documents` | Liệt kê tài liệu |
| `DELETE` | `/api/v1/documents/{doc_id}` | Xóa tài liệu và chunks |
| `POST` | `/api/v1/retrieval/search` | Vector hoặc hybrid search |
| `POST` | `/api/v1/chat/query` | Truy vấn RAG hoàn chỉnh |

OpenAPI documentation được cung cấp tại `/docs`.

### Validation

- `search_type`: chỉ nhận `vector` hoặc `hybrid`.
- `top_k`: từ `1` đến `100`.
- `chunk_size`: từ `1` đến `10.000`.
- `chunk_overlap`: lớn hơn hoặc bằng `0` và nhỏ hơn `chunk_size`.
- Query, title và content không được rỗng.
- File upload phải thuộc danh sách extension cho phép.
- Kích thước upload mặc định không quá 20 MB.

### Response chat

`POST /api/v1/chat/query` trả về:

```json
{
  "query": "Câu hỏi của người dùng",
  "answer": "Câu trả lời từ LLM",
  "retrieved_contexts": [
    {
      "chunk_id": "uuid",
      "document_id": "uuid",
      "chunk_index": 0,
      "content": "Nội dung chunk",
      "metadata": {},
      "score": 0.0327
    }
  ]
}
```

## 8. Cấu hình và triển khai

### Topology Docker Compose

```mermaid
flowchart LR
    Host[Host]
    API[rag_api<br/>FastAPI :8000]
    PG[rag_postgres<br/>PostgreSQL :5432]
    Volume[(pgdata)]

    Host -->|localhost:8000| API
    Host -->|localhost:45432| PG
    API -->|postgres:5432| PG
    PG --> Volume
```

### Database URL

| Ngữ cảnh | `DATABASE_URL` |
|---|---|
| API chạy trên máy host | `postgresql+psycopg://postgres:postgrespassword@localhost:45432/rag_db` |
| API chạy trong Compose | `postgresql+psycopg://postgres:postgrespassword@postgres:5432/rag_db` |

Chạy toàn bộ stack:

```bash
docker compose up --build
```

Container API chạy `alembic upgrade head` trước Uvicorn và chỉ khởi động sau
khi PostgreSQL vượt qua health check.

### Migration khi chạy không dùng Docker

Áp dụng toàn bộ migration:

```powershell
.\.venv\Scripts\alembic.exe upgrade head
```

Kiểm tra revision hiện tại:

```powershell
.\.venv\Scripts\alembic.exe current
```

Xem lịch sử migration:

```powershell
.\.venv\Scripts\alembic.exe history
```

Rollback một revision:

```powershell
.\.venv\Scripts\alembic.exe downgrade -1
```

Tạo revision mới sau khi thay đổi model:

```powershell
.\.venv\Scripts\alembic.exe revision --autogenerate -m "describe change"
```

Revision autogenerate phải được review thủ công trước khi chạy.

### Biến môi trường chính

| Biến | Mặc định | Mục đích |
|---|---|---|
| `DATABASE_URL` | PostgreSQL trên `localhost:45432` | Kết nối database |
| `EMBEDDING_PROVIDER` | `mock` | `openai`, `gemini` hoặc `mock` |
| `LLM_PROVIDER` | `mock` | `openai`, `gemini` hoặc `mock` |
| `OPENAI_API_KEY` | Rỗng | OpenAI authentication |
| `GEMINI_API_KEY` | Rỗng | Gemini authentication |
| `EMBEDDING_DIMENSION` | `1536` | Số chiều vector |
| `DEFAULT_CHUNK_SIZE` | `500` | Kích thước chunk |
| `DEFAULT_CHUNK_OVERLAP` | `50` | Độ chồng lấn |
| `DEFAULT_TOP_K` | `5` | Số context mặc định |
| `MAX_UPLOAD_SIZE_MB` | `20` | Giới hạn upload |
| `DB_INSERT_BATCH_SIZE` | `100` | Số chunk trong mỗi batch flush |
| `CORS_ORIGINS` | Local frontend origins | Danh sách origin được phép |

Tham khảo cấu hình đầy đủ trong `.env.example`.

## 9. Các quyết định thiết kế

### ADR-01: Modular monolith

**Quyết định:** Giữ API và các service trong một ứng dụng FastAPI.

**Lý do:** Triển khai đơn giản, dễ debug và phù hợp quy mô MVP.

**Hệ quả:** Khi ingestion hoặc query load tăng, cần tách background worker hoặc
dịch vụ độc lập.

### ADR-02: PostgreSQL làm unified store

**Quyết định:** Dùng PostgreSQL cho metadata, content, vector và full-text
search.

**Lý do:** Giảm số hệ thống phải vận hành và giữ transaction nhất quán.

**Hệ quả:** Full-text ranking hiện tại không tương đương BM25 chuyên dụng.

### ADR-03: HNSW với cosine distance

**Quyết định:** Dùng HNSW index và `vector_cosine_ops`.

**Lý do:** Cải thiện latency approximate nearest-neighbor search.

**Hệ quả:** Tốn thêm bộ nhớ và thời gian xây index.

### ADR-04: Reciprocal Rank Fusion

**Quyết định:** Dùng RRF để kết hợp vector và full-text ranking.

**Lý do:** Không cần chuẩn hóa hai thang điểm khác nhau.

**Hệ quả:** Cần đánh giá offline và điều chỉnh `top_k`.

### ADR-05: Provider adapter

**Quyết định:** Embedding và LLM được truy cập qua adapter.

**Lý do:** Có thể đổi provider thông qua cấu hình.

**Hệ quả:** Phải kiểm soát model, dimension và quy trình re-index.

### ADR-06: Fail fast khi thiếu API key

**Quyết định:** Provider thật phải báo lỗi khi thiếu API key.

**Lý do:** Tránh ứng dụng âm thầm fallback sang mock và tạo kết quả sai kỳ vọng.

### ADR-07: Alembic là nguồn quản lý schema

**Quyết định:** Application không gọi `create_all()` hoặc tạo index khi
startup. Mọi thay đổi schema phải đi qua Alembic revision.

**Lý do:** Schema có lịch sử, có thể review, triển khai và rollback có kiểm
soát.

**Hệ quả:** Phải chạy `alembic upgrade head` trước khi khởi động API. Với nhiều
API replica, production nên chạy migration bằng một deployment job riêng.

## 10. Bảo mật và vận hành

### Hiện trạng

- CORS mặc định chỉ cho phép `localhost:3000` và `localhost:5173`.
- Upload được giới hạn loại file và kích thước.
- Provider thiếu API key sẽ thất bại rõ ràng.
- Health check kiểm tra cả database và pgvector.

### Chưa có

- Authentication.
- Authorization theo document hoặc tenant.
- Rate limiting.
- Secret manager.
- Antivirus/file scanning.
- Structured logging.
- Metrics và distributed tracing.
- Circuit breaker cho AI provider.

> Không nên mở API hiện tại trực tiếp ra Internet trước khi bổ sung
> authentication, authorization và rate limiting.

## 11. Kiểm thử

Bộ kiểm thử hiện có 21 trường hợp, bao phủ:

- Chunk splitting.
- Các cửa sổ chunk không hợp lệ.
- Mock embedding có tính deterministic và normalized.
- Provider thiếu API key.
- Prompt có context và citation.
- Mock LLM khi không có context.
- Pydantic request validation.
- Rollback khi embedding thất bại.
- `VectorStoreService.add_chunks()` không tự commit.
- Loại bỏ NUL/control characters trước khi lưu.
- Phát hiện PDF có text layer lỗi.

Các kiểm tra đã thực hiện:

```text
21 tests passed
Python compile check passed
OpenAPI schema validation passed
Docker Compose configuration passed
```

## 12. Backlog trước production

### P0

- Authentication và authorization theo document/tenant.
- Rate limiting.
- Quy trình backup và diễn tập rollback database migration.

### P1

- Background worker cho ingestion.
- Batch embedding.
- Retry có exponential backoff.
- Idempotency key cho ingestion.
- Structured logging, metrics và tracing.
- Integration test với PostgreSQL/pgvector.
- Contract test với AI provider.

### P2

- Reranker.
- Evaluation dataset.
- Đo `recall@k`, groundedness và answer correctness.
- Thiết lập latency/error-rate SLO.
- OCR.
- Antivirus scan.
- Object storage cho file gốc.

## 13. Tiêu chí nghiệm thu kiến trúc

1. `alembic upgrade head` tạo extension, bảng và index thành công.
2. `docker compose up --build` đưa database và API về trạng thái healthy.
3. Upload sai loại, quá kích thước hoặc chunk window sai bị từ chối.
4. Lỗi embedding không để lại document hoặc chunk ghi dở.
5. Vector và hybrid search tôn trọng `document_id`.
6. Chat response trả về cả câu trả lời và `retrieved_contexts`.
7. Provider thiếu API key không fallback sang mock.
8. Bộ kiểm thử và OpenAPI validation tiếp tục đạt trong CI.

## 14. Bản đồ mã nguồn

```text
RAG/
├── main.py
├── app/
│   ├── config.py
│   ├── database.py
│   ├── models.py
│   ├── api/
│   │   ├── routes.py
│   │   └── schemas.py
│   └── services/
│       ├── parser.py
│       ├── chunker.py
│       ├── embedding.py
│       ├── vector_store.py
│       ├── prompt_builder.py
│       └── llm.py
├── tests/
│   └── test_rag_pipeline.py
├── migrations/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       ├── 20260728_0001_initial_rag_schema.py
│       ├── cfc53009db86_describe_change.py
│       └── 20260728_0002_restore_fts_index.py
├── alembic.ini
├── Dockerfile
├── docker-entrypoint.sh
├── docker-compose.yml
├── requirements.txt
└── .env.example
```
