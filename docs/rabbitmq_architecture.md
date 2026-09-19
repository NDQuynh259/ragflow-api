# Kiến Trúc Toàn Diện Message Queue & Luồng Hoạt Động (RabbitMQ Platform Architecture)

Tài liệu này là đặc tả kiến trúc chuẩn (**Single Source of Truth**) cho toàn bộ hệ thống **Message Queue Core** của RAG Platform. Tài liệu mô tả chi tiết từ tầng Producer, Broker Topology, Consumer Engine, các bài toán mở rộng (Scale ngang, Idempotency, Delayed Retry, DLQ), cho đến cam kết độ bền vững (Durability) chống mất dữ liệu khi mất điện.

---

## 1. Tổng Quan Kiến Trúc & Các Trụ Cột Cốt Lõi

Hệ thống RAG giải quyết bài toán xử lý tài liệu lớn (PDF, Word, OCR, Heading-aware Chunking, Gemini Embeddings, PGVector) — những tác vụ tiêu tốn nhiều CPU, RAM và I/O mạng (mất từ vài giây đến hàng chục phút). 

Để đảm bảo Web API (`chat-api`) luôn phản hồi cực nhanh (< 50ms) và hệ thống vận hành ổn định ở quy mô lớn, Message Queue Core được xây dựng dựa trên **6 trụ cột kiến trúc cốt lõi**:

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    6 TRỤ CỘT MESSAGE QUEUE CORE                                  │
├──────────────────┬──────────────────┬──────────────────┬──────────────────┬──────────────────────┤
│ 1. PRODUCER      │ 2. CONSUMER      │ 3. RETRY & DLQ   │ 4. IDEMPOTENCY   │ 5. COMPETING WORKERS │
│ • JobEnvelope    │ • Prefetch = 1   │ • Delayed Retry  │ • Atomic State   │ • Exclusive Channel  │
│ • UUIDv7 Job ID  │ • Manual ACK     │   Queue (TTL)    │   Gate (Postgres)│ • Round-Robin        │
│ • Publisher      │ • JobDispatcher  │ • Exponential    │ • Idempotent     │ • consumer_timeout   │
│   Confirms       │ • Async Engine   │   Backoff        │   Clean Writes   │   Protection         │
│ • Persistent Mode│   (aio-pika)     │ • Dead Letter Q  │ • Skip Duplicates│ • Linear Scale-Out   │
├──────────────────┴──────────────────┴──────────────────┴──────────────────┴──────────────────────┤
│ 6. DURABILITY (CHỐNG MẤT DỮ LIỆU KHI MẤT ĐIỆN):                                                  │
│ Durable Exchanges + Durable Queues + Persistent Delivery Mode (2) + Docker Volume Mount          │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Sơ Đồ Luồng Hoạt Động Tổng Thể (End-to-End Workflow)

### 2.1. Sơ Đồ Trình Tự Chi Tiết (Sequence Diagram)
Mô tả toàn bộ vòng đời của một tác vụ từ khi Client gửi yêu cầu, qua Producer, Broker, Worker, cơ chế Retry/DLQ, và phát sự kiện thời gian thực (SSE) về Client:

```mermaid
sequenceDiagram
    autonumber
    actor Client as 💻 Frontend / Client
    participant API as 🌐 apps/chat-api
    participant DB as 🗄️ PostgreSQL (pgvector)
    participant Producer as 📤 RabbitMQQueueAdapter (pika)
    participant Broker as 🐰 RabbitMQ Broker (rag.direct)
    participant RetryQ as ⏳ Retry Queue (TTL Backoff)
    participant DLQ as 💀 Dead Letter Queue (.dlq)
    participant Worker as ⚙️ apps/worker (Async Consumer)
    participant Dispatcher as 🎯 JobDispatcher
    participant Processor as 📑 process_index_document
    participant SSE as 📡 SSE Hub (rag.events)

    %% BƯỚC 1: CLIENT UPLOAD & PRODUCER ĐẨY JOB
    rect rgb(240, 249, 255)
    Note over Client,Producer: 1. GIAI ĐOẠN ĐẨY JOB (PRODUCER SIDE)
    Client->>+API: POST /api/v1/workspaces/{id}/documents (Upload File)
    API->>DB: INSERT document (status='queued'), ingestion_job (status='queued')
    API->>+Producer: enqueue(action='index', payload={doc_id, storage_uri, ws_id})
    Note over Producer: Đóng gói JobEnvelope:<br/>• job_id: UUIDv7<br/>• correlation_id: trace-xyz<br/>• retry_count: 0, max_retries: 3
    Producer->>Broker: basic_publish(exchange='rag.direct', routing='document.ingestion', delivery_mode=2)
    Note over Broker: Ghi đĩa Write-Ahead Log (WAL)
    Broker-->>Producer: Publisher Confirm (ACK ghi đĩa thành công)
    Producer-->>-API: Trả về job_id
    API-->>-Client: HTTP 201 Created (document_id, job_id, status='queued')
    end

    %% BƯỚC 2: CONSUMER NHẬN JOB & ATOMIC STATE GATE
    rect rgb(240, 253, 244)
    Note over Broker,SSE: 2. GIAI ĐOẠN XỬ LÝ (CONSUMER SIDE - PREFETCH=1)
    Broker->>+Worker: Dispatch 1 Message (Unacknowledged)
    Worker->>Dispatcher: dispatch(envelope)
    Dispatcher->>+Processor: Gọi hàm xử lý (offload sang thread pool)

    %% Lớp bảo vệ Idempotency
    Note over Processor,DB: Kiểm tra Idempotency (Atomic State Gate)
    Processor->>DB: UPDATE ingestion_jobs SET status='PROCESSING' WHERE id=:job_id AND status IN ('PENDING','FAILED')
    alt rowcount == 0 (Job đang chạy hoặc đã xong)
        Processor-->>Dispatcher: Duplicate detected (Skip)
        Dispatcher-->>Worker: No-op
        Worker->>Broker: basic_ack() (Xóa message trùng)
    else rowcount == 1 (Nhận quyền xử lý hợp lệ)
        Processor->>SSE: Publish Event: document_progress (10%, step="started")
        SSE-->>Client: event: document_progress (data: 10%)
        
        Note over Processor: Đọc file, Parse PDF, Heading-aware Chunking
        Processor->>SSE: Publish Event: document_progress (50%, step="parsed")
        SSE-->>Client: event: document_progress (data: 50%)
        
        Note over Processor: Gọi Gemini Embeddings (768 dims)
        Processor->>DB: DELETE FROM document_chunks WHERE document_id=:doc_id (Clean write)
        Processor->>DB: INSERT new chunks & vector embeddings
        Processor->>DB: UPDATE documents status='ready', jobs status='completed'
        
        Processor->>SSE: Publish Event: document_ready (100%)
        SSE-->>Client: event: document_ready (Hoàn tất)
        Processor-->>Dispatcher: Success
        Dispatcher-->>Worker: Done
        Worker->>Broker: basic_ack() (Xác nhận hoàn tất thành công)
    end
    deactivate Processor
    deactivate Worker
    end

    %% BƯỚC 3: CƠ CHẾ DELAYED RETRY KHI GẶP SỰ CỐ
    rect rgb(255, 251, 235)
    Note over Worker,RetryQ: 3. GIAI ĐOẠN RETRY (DELAYED RETRY VỚI TTL)
    opt Khi Processor ném Ngoại lệ (API Timeout / Mất mạng / Lỗi tạm thời)
        Worker->>Worker: Kiểm tra retry_count < max_retries (ví dụ: 1 < 3)
        Note over Worker: Tính Backoff: 10s * 2^(retry_count - 1)<br/>retry_count += 1
        Worker->>RetryQ: Publish vào rag.document.ingestion.retry (TTL = 10,000ms)
        Worker->>Broker: basic_ack() trên message cũ
        Note over RetryQ: Chờ hết 10 giây TTL...<br/>RabbitMQ tự động kích hoạt Dead-Letter Exchange (DLX)
        RetryQ->>Broker: Tự động đẩy ngược về Main Queue (rag.document.ingestion)
    end
    end

    %% BƯỚC 4: DEAD LETTER QUEUE KHI VƯỢT QUÁ RETRY
    rect rgb(255, 241, 242)
    Note over Worker,DLQ: 4. GIAI ĐOẠN CÁCH LY LỖI (DEAD LETTER QUEUE)
    opt Khi retry_count >= max_retries (Đã thử lại 3 lần vẫn lỗi)
        Worker->>DLQ: Chuyển message vào rag.document.ingestion.dlq
        Worker->>DB: UPDATE documents status='failed', jobs status='failed'
        Worker->>SSE: Publish Event: document_failed (error_details)
        SSE-->>Client: event: document_failed (Báo lỗi cho User)
        Worker->>Broker: basic_ack() / basic_reject(requeue=False)
    end
    end
```

---

## 3. Kiến Trúc Topology Hàng Đợi (RabbitMQ Broker Topology)

Hệ thống sử dụng **Topology 3 tầng** nhằm tách biệt tuyệt đối giữa:
1. **Hàng đợi chính (Main Queue)**: Tiếp nhận việc mới.
2. **Hàng đợi hoãn thử lại (Delayed Retry Queue)**: Giữ tin nhắn đang chờ thời gian backoff.
3. **Hàng đợi chết (Dead Letter Queue)**: Chứa các tin nhắn độc (poison pills) hoặc hỏng hoàn toàn.

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'fontFamily': 'Inter, system-ui, sans-serif' }}}%%
flowchart TD
    classDef producer fill:#0284c7,stroke:#0369a1,stroke-width:2px,color:#ffffff,font-weight:bold;
    classDef exchange fill:#f97316,stroke:#c2410c,stroke-width:2px,color:#ffffff,font-weight:bold;
    classDef queue fill:#ea580c,stroke:#9a3412,stroke-width:2px,color:#ffffff,font-weight:bold;
    classDef retry fill:#eab308,stroke:#ca8a04,stroke-width:2px,color:#0f172a,font-weight:bold;
    classDef dlq fill:#f43f5e,stroke:#be123c,stroke-width:2px,color:#ffffff,font-weight:bold;
    classDef worker fill:#10b981,stroke:#047857,stroke-width:2px,color:#ffffff,font-weight:bold;

    API["🌐 chat-api (Producer)"]:::producer

    subgraph MAIN_LAYER ["TẦNG 1: MAIN PROCESSING LAYER"]
        DirectEx{{"Exchange: rag.direct\n(Type: direct, Durable)"}}:::exchange
        MainQ[["Queue: rag.document.ingestion\n(Durable, prefetch=1)"]]:::queue
    end

    subgraph RETRY_LAYER ["TẦNG 2: DELAYED RETRY LAYER (TTL)"]
        RetryEx{{"Exchange: rag.direct.retry\n(Type: direct, Durable)"}}:::retry
        RetryQ[["Queue: rag.document.ingestion.retry\n(Durable, x-message-ttl: Dynamic,\nx-dead-letter-exchange: rag.direct,\nx-dead-letter-routing-key: document.ingestion)"]]:::retry
    end

    subgraph DLQ_LAYER ["TẦNG 3: DEAD LETTER LAYER (DLQ)"]
        DLX{{"Exchange: rag.direct.dlx\n(Type: direct, Durable)"}}:::dlq
        DLQueue[["Queue: rag.document.ingestion.dlq\n(Durable, Lưu trữ để phân tích sự cố)"]]:::dlq
    end

    Worker["⚙️ apps/worker (Competing Consumers)"]:::worker

    %% Routing
    API ==>|"1. Publish (delivery_mode=2)"| DirectEx
    DirectEx -->|"routing: document.ingestion"| MainQ
    MainQ ==>|"2. Dispatch 1 job (Fair dispatch)"| Worker

    %% Outcomes
    Worker -.->|"3a. Thành công: basic_ack()"| MainQ
    Worker ==>|"3b. Thất bại & retry < 3:\nPublish kèm TTL (10s, 20s, 40s)"| RetryEx
    RetryEx -->|"routing: document.ingestion.retry"| RetryQ
    RetryQ ==>|"4. Hết hạn TTL:\nAuto Dead-Letter về Main Queue"| DirectEx

    Worker ==>|"3c. Thất bại & retry >= 3:\nChuyển vào DLQ"| DLX
    DLX -->|"routing: document.ingestion.dlq"| DLQueue
```

---

## 4. Chi Tiết Kỹ Thuật 6 Trụ Cột

### 4.1. Trụ Cột 1: Producer Đẩy Job Vào Hàng Đợi
- **Đóng gói chuẩn hóa (`JobEnvelope`)**:
  Mọi thông điệp trao đổi qua message broker đều phải tuân theo cấu trúc schema `JobEnvelope` (học hỏi từ chuẩn `ViShop` kết hợp tối ưu cho RAG):
  ```json
  {
    "job_id": "0191eb5d-8a21-7000-8000-000000000001",
    "action": "index",
    "payload": {
      "document_id": "0191eb5d-8a21-7000-8000-000000000002",
      "storage_uri": "output/storage/ws-1/report.pdf",
      "workspace_id": "0191eb5d-8a21-7000-8000-000000000000"
    },
    "enqueued_at": "2026-09-19T05:00:00.000Z",
    "correlation_id": "req-9b1c7f42-4321-7890",
    "retry_count": 0,
    "max_retries": 3,
    "routing_key": "document.ingestion"
  }
  ```
- **Publisher Confirms (`channel.confirm_delivery()`)**:
  Trong synchronous adapter (`pika`), Producer kích hoạt chế độ xác nhận phân phối. Khi gọi `basic_publish`, client sẽ chờ tín hiệu xác nhận từ broker để chắc chắn message đã được an toàn ghi vào đĩa trước khi trả về kết quả cho ứng dụng.

---

### 4.2. Trụ Cột 2: Consumer Nhận Job & Phân Phối
- **QoS Fair Dispatch (`prefetch_count=1`)**:
  Trong môi trường xử lý tài liệu lớn, tài nguyên CPU và RAM là có hạn. Nếu không đặt `prefetch_count`, một worker có thể bị RabbitMQ dồn 5-10 file PDF cùng lúc dẫn đến tràn bộ nhớ (Out of Memory - OOM).
  $\rightarrow$ Đặt `prefetch_count = 1` đảm bảo **mỗi worker chỉ nhận đúng 1 tài liệu tại một thời điểm**.
- **Manual Acknowledgement (`no_ack=False`)**:
  Message không bao giờ bị xóa tự động. Chỉ khi hàm xử lý nghiệp vụ chạy hoàn tất không có exception, worker mới phát lệnh `await message.ack()`.
- **`JobDispatcher`**:
  Tách biệt logic hạ tầng kết nối khỏi logic nghiệp vụ. Tương tự cấu trúc `processors/` của ViShop, các handler nghiệp vụ được đăng ký theo hành động (`action`):
  ```python
  dispatcher = JobDispatcher()
  dispatcher.register("index", process_index_document)
  dispatcher.register("reindex", process_index_document)
  dispatcher.register("delete", process_delete_document)
  ```

---

### 4.3. Trụ Cột 3: Cơ Chế Delayed Retry & Dead Letter Queue (DLQ)
- **Vấn đề của `nack(requeue=True)`**: Khi gặp file PDF bị mã hóa hoặc API bên thứ ba tạm thời nghẽn, việc đẩy lại ngay đầu queue sẽ gây ra bão request (thử lại hàng nghìn lần/giây, 100% CPU).
- **Giải pháp Delayed Retry với TTL**:
  * Khi worker bắt được lỗi: kiểm tra `envelope.retry_count`.
  * Nếu `retry_count < max_retries`:
    * Tăng `retry_count += 1`.
    * Tính thời gian chờ theo công thức lũy thừa:
      $$\text{Delay (ms)} = \text{Initial Delay} \times 2^{(\text{retry\_count} - 1)}$$
      *(Lần 1: 10,000ms = 10s; Lần 2: 20,000ms = 20s; Lần 3: 40,000ms = 40s)*.
    * Đẩy message vào `rag.document.ingestion.retry` kèm header `expiration: str(delay)`.
    * Gửi `ACK` trên message cũ.
    * **Sau khi hết hạn TTL**: Nhờ cấu trúc `x-dead-letter-exchange: rag.direct` và `x-dead-letter-routing-key: document.ingestion`, **RabbitMQ tự động đẩy message ngược về hàng đợi chính** mà không cần bất kỳ tiến trình scheduler nào phải quét polling!
  * Nếu `retry_count >= max_retries`:
    * Chuyển message vào `rag.document.ingestion.dlq`.
    * Đánh dấu bản ghi trong DB thành `FAILED` kèm `error_details`.
    * Bắn sự kiện SSE `document_failed` về client.

---

### 4.4. Trụ Cột 4: Chống Trùng Lặp Job (Idempotency)
Do hệ thống phân tán luôn tuân thủ nguyên lý **At-Least-Once Delivery**, sự cố rớt mạng ngay trước khi gửi `ACK` có thể khiến RabbitMQ cấp lại message đó cho một worker khác (`redelivered=True`).

Hệ thống RAG sử dụng **2 tầng phòng thủ**:

1. **Tầng 1: Atomic State Gate trên PostgreSQL**:
   Trước khi tiến hành đọc file hay gọi AI embedding, worker thực thi một câu lệnh cập nhật nguyên tử:
   ```sql
   UPDATE ingestion_jobs
      SET status = 'PROCESSING',
          started_at = NOW(),
          updated_at = NOW()
    WHERE id = :job_id
      AND status IN ('PENDING', 'FAILED');
   ```
   * Nếu `rowcount == 0`: Nghĩa là job này đã có worker khác nhận xử lý (đang `PROCESSING`) hoặc đã xong (`COMPLETED`). Worker hiện tại lập tức gửi `ACK` và bỏ qua (skip), loại bỏ hoàn toàn trùng lặp.
   * Nếu `rowcount == 1`: Worker giành quyền xử lý duy nhất và tiếp tục.

2. **Tầng 2: Idempotent Database Writes**:
   Trong bước lưu trữ vector:
   ```sql
   DELETE FROM document_chunks WHERE document_id = :document_id;
   ```
   Sau đó mới chèn các chunk mới. Dù job có bị chạy lại 2 lần thì dữ liệu vector trong CSDL vẫn luôn hoàn toàn nhất quán.

---

### 4.5. Trụ Cột 5: Scale Ngang Hàng Đợi (Competing Consumers)
Khi tải tăng cao, quản trị viên có thể scale số lượng worker container lên $N$ instance:
```bash
docker compose up -d --scale worker=5
```
- **Cơ chế Competing Consumers của RabbitMQ**:
  * RabbitMQ chia sẻ cùng một queue `rag.document.ingestion` cho cả 5 worker.
  * Khi có message đến, RabbitMQ phân phối theo thuật toán Round-Robin.
  * Ngay khi message được gửi tới Worker A, RabbitMQ đánh dấu message là `Unacknowledged` trên kênh của Worker A. Các Worker B, C, D **hoàn toàn không nhìn thấy và không thể can thiệp**.
- **Cấu hình `consumer_timeout`**:
  * RabbitMQ mặc định có cờ `consumer_timeout` (mặc định 30 phút). Nếu một file PDF 100 trang mất 15 phút để OCR và Chunking, kết nối AMQP vẫn gửi heartbeat liên tục để chứng minh worker còn sống, tránh tình trạng broker tưởng worker chết mà cấp lại job cho worker khác.

---

### 4.6. Trụ Cột 6: Độ Bền Vững (Durability) - Chống Mất Dữ Liệu Khi Mất Điện
Cam kết **0% mất mát thông điệp** thông qua Bộ 4 Trụ Cột:

```mermaid
flowchart LR
    subgraph PILLARS ["BỘ 4 TRỤ CỘT BẢO TỒN DỮ LIỆU KHI MẤT ĐIỆN"]
        P1["1. Durable Exchanges & Queues\n(durable=True)\nLưu metadata trên đĩa"]
        P2["2. Persistent Message Mode\n(delivery_mode=2)\nGhi WAL message trên đĩa"]
        P3["3. Manual Acknowledgement\n(no_ack=False)\nChỉ xóa khỏi đĩa khi xong"]
        P4["4. Docker Persistent Volume\n(/var/lib/rabbitmq mount volume)\nBảo toàn đĩa vật lý của host"]
    end
```

1. **Durable Exchange & Queue**: Toàn bộ Exchange (`rag.direct`, `rag.direct.retry`, `rag.direct.dlx`) và Queue (`rag.document.ingestion`, `rag.document.ingestion.retry`, `rag.document.ingestion.dlq`) được khai báo với `durable = True`.
2. **Persistent Message**: Mọi tin nhắn được publish với `delivery_mode = 2` (`Persistent`). RabbitMQ bắt buộc phải ghi dữ liệu xuống đĩa cứng (Write-Ahead Log) trước khi đưa vào bộ nhớ RAM.
3. **Manual Acknowledgement**: Tin nhắn chỉ được xóa khỏi đĩa khi worker xử lý xong và gửi `ACK`. Nếu nguồn điện phụt tắt giữa chừng, tin nhắn vẫn còn nguyên trên đĩa.
4. **Docker Persistent Volume**:
   Trong file `deploy/docker-compose.prod.yml`, thư mục dữ liệu của RabbitMQ được ánh xạ ra volume vật lý:
   ```yaml
   rabbitmq:
     image: rabbitmq:3.13-management-alpine
     volumes:
       - rabbitmq_data_prod:/var/lib/rabbitmq
   ```
   Khi máy chủ bật lại và container khởi động, RabbitMQ sẽ tự động phục hồi toàn bộ tin nhắn từ volume đĩa cứng và tiếp tục phân phối cho các worker.

---

## 5. Bảng Tham Số Cấu Hình Hệ Thống

| Tên Biến Môi Trường | Giá Trị Mặc Định | Ý Nghĩa / Mục Đích |
|---|---|---|
| `RABBITMQ_URL` | `amqp://guest:guest@localhost:5672/` | Địa chỉ kết nối AMQP của RabbitMQ Broker |
| `RABBITMQ_EXCHANGE` | `rag.direct` | Tên Direct Exchange chính tiếp nhận job |
| `RABBITMQ_INGESTION_QUEUE` | `rag.document.ingestion` | Tên hàng đợi chính xử lý ingestion |
| `RABBITMQ_ROUTING_KEY` | `document.ingestion` | Khóa định tuyến từ Exchange chính vào Queue chính |
| `RABBITMQ_PREFETCH_COUNT` | `1` | Số lượng job tối đa cấp cho 1 worker tại 1 thời điểm |
| `RABBITMQ_MAX_RETRIES` | `3` | Số lần retry tối đa trước khi đưa vào DLQ |
| `RABBITMQ_INITIAL_RETRY_DELAY_MS` | `10000` | Thời gian chờ cho lần retry đầu tiên (10 giây) |
| `RABBITMQ_EVENTS_EXCHANGE` | `rag.events` | Topic Exchange dành riêng cho phát sự kiện thời gian thực SSE |

---

## 6. Hướng Dẫn Vận Hành & Giám Sát

### 6.1. Giám Sát Qua Giao Diện RabbitMQ Management Web UI
- **URL**: `http://localhost:15672` (hoặc port 15672 trên production server)
- **Tài khoản mặc định**: `guest` / `guest`

#### Các chỉ số quan trọng cần quan sát:
1. **Queued Messages (Overview)**:
   * `Ready`: Số job đang nằm chờ worker. Nếu chỉ số này tăng liên tục $\rightarrow$ Cần scale thêm worker (`docker compose up -d --scale worker=X`).
   * `Unacked`: Số job đang được các worker xử lý. Con số này thông thường sẽ bằng đúng số worker container đang chạy (do `prefetch_count=1`).
2. **Dead Letter Queue (`rag.document.ingestion.dlq`)**:
   * Kiểm tra định kỳ xem có tin nhắn đọng trong DLQ hay không. Bấm vào queue $\rightarrow$ **Get messages** để đọc nội dung `payload` và `correlation_id` nhằm điều tra nguyên nhân.

---

## 7. Tổng Kết & Mã Nguồn Tương Ứng

| Tầng Kiến Trúc | File Mã Nguồn Đại Diện | Vai Trò Chính |
|---|---|---|
| **Data Contract** | [`core.queue.schema`](file:///c:/Users/ndquynh/Documents/RAG/core/src/core/queue/schema.py) | Định nghĩa `JobEnvelope`, serialize/deserialize JSON/Bytes |
| **Port Interface** | [`core.queue.port`](file:///c:/Users/ndquynh/Documents/RAG/core/src/core/queue/port.py) | `JobQueuePort` & `IngestionQueuePort` (tương thích ngược 100%) |
| **Producer Adapter** | [`core.queue.rabbitmq`](file:///c:/Users/ndquynh/Documents/RAG/core/src/core/queue/rabbitmq.py) | `RabbitMQQueueAdapter` (sync `pika`, publisher confirms, setup DLX/Retry) |
| **Consumer Engine** | [`core.queue.consumer`](file:///c:/Users/ndquynh/Documents/RAG/core/src/core/queue/consumer.py) | `AsyncRabbitMQConsumer` (`aio-pika`, prefetch=1, delayed retry TTL, DLQ) |
| **Dispatcher** | [`core.queue.consumer.JobDispatcher`](file:///c:/Users/ndquynh/Documents/RAG/core/src/core/queue/consumer.py) | Đăng ký & điều phối hành động sang handler chuyên biệt |
| **Worker Application** | [`apps.worker.main`](file:///c:/Users/ndquynh/Documents/RAG/apps/worker/src/worker/main.py) | Bootstrap ứng dụng worker, đăng ký processors |
| **Index Processor** | [`apps.worker.processors.index_document`](file:///c:/Users/ndquynh/Documents/RAG/apps/worker/src/worker/processors/index_document.py) | Xử lý file PDF, chunking, embedding, atomic state gate |
