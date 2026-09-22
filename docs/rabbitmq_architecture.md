# Kiến Trúc Toàn Diện RabbitMQ & Ứng Dụng Trong RAG Platform

Tài liệu này là đặc tả kiến trúc chuẩn (**Single Source of Truth**) về Message Queue của dự án RAG Platform. Tài liệu được cấu trúc làm 2 phần rõ rệt:
1. **Phần 1**: Nguyên lý kiến trúc bền vững 4 bước chuẩn của RabbitMQ (**RabbitMQ 4-Step Reliability Architecture**) như trong sơ đồ thiết kế.
2. **Phần 2**: Hiện thực hóa và ứng dụng toàn diện kiến trúc trên vào hệ thống RAG Platform (Producer, Routing, Quorum Queues, Consumer Engine, Delayed Retry TTL, DLQ, Idempotency và Durability).

---

# PHẦN 1: KIẾN TRÚC BỀN VỮNG 4 BƯỚC CỦA RABBITMQ (THE 4-STEP RELIABILITY LIFECYCLE)

Để đạt được cam kết **0% mất mát thông điệp (Zero Message Loss / At-Least-Once Delivery)** trong môi trường phân tán, RabbitMQ xây dựng một chu trình bảo vệ 4 giai đoạn khép kín:

![RabbitMQ 4-Step Reliability Lifecycle](./assets/rabbitmq_reliability_flow.png)

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                           CHU TRÌNH 4 BƯỚC BẢO TOÀN THÔNG ĐIỆP RABBITMQ                          │
├─────────────────────┬─────────────────────┬───────────────────────┬──────────────────────────────┤
│ 1. PUBLISHER CONFIRM│ 2. ROUTING          │ 3. QUORUM REPLICATION │ 4. CONSUMER ACK              │
│ Broker xác nhận đã  │ Exchange định tuyến │ Tin nhắn được sao chép│ Consumer xác nhận đã         │
│ nhận tin nhắn       │ tin nhắn đến queue  │ an toàn trên cluster  │ xử lý thành công             │
│ • channel.confirm() │ • Direct / Topic    │ • Raft Consensus      │ • basic_ack()                │
│ • Chống mất trên bus│ • Binding Rules     │ • Ghi đĩa WAL đa số   │ • basic_nack(requeue=False)  │
│ • Persistent Mode 2 │ • Alternate Exchange│ • Chịu lỗi sập node   │ • Prefetch QoS = 1           │
└─────────────────────┴─────────────────────┴───────────────────────┴──────────────────────────────┘
```

---

### Bước 1: Publisher Confirm (Xác Nhận Đầu Vào Từ Broker)

* **Vấn đề**: Trong giao thức AMQP mặc định, Producer gửi tin nhắn theo cơ chế "gửi rồi quên" (fire-and-forget). Nếu mạng bị chập chờn, broker bị tràn RAM hoặc kết nối bị đứt đúng thời điểm gửi, tin nhắn sẽ biến mất mà ứng dụng không hề hay biết.
* **Bản chất kỹ thuật**:
  * Khi kích hoạt chế độ **Publisher Confirms** (`channel.confirm_delivery()`):
    1. Kênh AMQP được chuyển sang trạng thái theo dõi xác nhận (Confirm Mode).
    2. Mỗi tin nhắn gửi đi được cấp một số thứ tự nguyên tuần tự (`delivery_tag`).
    3. Sau khi Broker tiếp nhận tin nhắn và **lưu trữ an toàn vào đĩa cứng (hoặc nhân bản xong ở bước 3)**, Broker sẽ phát tín hiệu phản hồi `basic_ack` kèm `delivery_tag` tương ứng về cho Producer.
    4. Nếu xảy ra lỗi nội bộ (hết đĩa, sập phân vùng), Broker sẽ gửi `basic_nack`.
* **Ý nghĩa**: Ngăn chặn triệt để tình trạng mất dữ liệu **ngay tại cửa ngõ đầu vào (In-flight loss)**. Ứng dụng chỉ coi tác vụ đã gửi thành công khi nhận được tín hiệu ACK này.

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': { 'darkMode': true, 'signalTextColor': '#ffffff', 'actorTextColor': '#ffffff', 'signalColor': '#38bdf8', 'lineColor': '#38bdf8' }}}%%
sequenceDiagram
    autonumber
    participant Producer as Publisher - Producer App
    participant Broker as RabbitMQ Broker
    participant Disk as Write-Ahead Log Disk

    Producer->>Broker: basic_publish (delivery_mode=2, payload)
    Note over Broker: Broker tiếp nhận tin nhắn
    Broker->>Disk: Ghi dữ liệu xuống đĩa WAL
    Disk-->>Broker: Xác nhận đã ghi đĩa
    Broker-->>Producer: basic_ack (Publisher Confirm thành công)
```

---

### Bước 2: Routing (Định Tuyến Qua Exchange Đến Queue)

* **Vấn đề**: Trong RabbitMQ, Producer **không bao giờ gửi trực tiếp vào Queue**. Tin nhắn nếu không tìm thấy hàng đợi nào khớp quy tắc sẽ bị drop âm thầm (unroutable message).
* **Bản chất kỹ thuật**:
  * Producer luôn gửi tin nhắn vào một **Exchange** cùng với nhãn định tuyến **Routing Key**.
  * Exchange đóng vai trò "bưu điện trung tâm", áp dụng các thuật toán định tuyến dựa trên các liên kết (**Bindings**):
    * **Direct Exchange**: Khớp chính xác hoàn toàn giữa `Routing Key` và `Binding Key` (dùng cho tác vụ định danh chính xác như Ingestion job).
    * **Topic Exchange**: Khớp theo mẫu ký tự đại diện wildcard `*` (1 từ) và `#` (nhiều từ) (dùng cho luồng sự kiện Realtime SSE theo workspace).
    * **Fanout Exchange**: Bỏ qua routing key, phát sóng đồng thời tới mọi Queue được liên kết.
  * **Cơ chế an toàn (Mandatory Flag & Alternate Exchange)**: Nếu cấu hình cờ `mandatory=True`, khi không có hàng đợi nào nhận tin, Broker sẽ trả ngược tin nhắn về cho Producer qua sự kiện `basic_return`. Hoặc cấu hình **Alternate Exchange (AE)** để hứng tất cả các tin nhắn không định tuyến được.
* **Ý nghĩa**: Tách rời hoàn toàn người phát tin (Publisher) và người nhận tin (Consumer). Cho phép phân luồng dữ liệu sang Main Queue, Retry Queue hoặc DLQ một cách linh hoạt.

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': { 'darkMode': true, 'edgeLabelBackground': '#1e293b' }}}%%
flowchart LR
    Pub[Publisher] -->|publish key=document.ingestion| Ex{Exchange: rag.direct}
    Ex -->|Binding: document.ingestion| Q1[Queue Chính: rag.document.ingestion]
    Ex -->|Binding: events| Q2[Queue SSE Sự Kiện]
    Ex -->|Unroutable / Fallback| AE[Alternate Exchange]
```

---

### Bước 3: Quorum Replication (Sao Chép Dữ Liệu Bền Vững Đa Máy Chủ)

* **Vấn đề**: Nếu RabbitMQ chỉ chạy trên 1 máy chủ đơn lẻ, khi máy chủ bị mất điện, cháy ổ cứng hoặc crash hệ điều hành, toàn bộ hàng đợi sẽ ngừng hoạt động và dữ liệu trong RAM có thể bị biến mất.
* **Bản chất kỹ thuật**:
  * **Quorum Queues** là công nghệ hàng đợi thế hệ mới (hiện đại nhất) của RabbitMQ, xây dựng trên thuật toán đồng thuận phân tán **Raft Consensus Protocol**:
    1. Một Quorum Queue được triển khai trên một cụm máy chủ (**RabbitMQ Cluster**, thông thường 3 hoặc 5 nodes).
    2. Một node đóng vai trò **Raft Leader**, các node còn lại đóng vai trò **Raft Followers**.
    3. Khi tin nhắn được đưa vào Queue, Leader sẽ gửi bản ghi log tuần tự (Log Entries) tới tất cả các Followers.
    4. Khi **đa số node (Quorum = $\lfloor N/2 \rfloor + 1$)** xác nhận đã ghi dữ liệu vào đĩa cứng (WAL), giao dịch được coi là đã Commit.
    5. Chỉ sau khi đạt Quorum ghi đĩa, Broker mới gửi `Publisher Confirm` (ở Bước 1) về cho Producer.
* **Ý nghĩa**: **Khả năng chịu lỗi cực cao (High Availability & Fault Tolerance)**. Dù 1 node bị sập hoặc mất điện đột ngột, cụm cluster tự động bầu Leader mới trong vài mili-giây và tiếp tục hoạt động mà **không mất 1 byte dữ liệu nào**.

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': { 'darkMode': true, 'edgeLabelBackground': '#1e293b' }}}%%
flowchart TD
    subgraph CLUSTER [RabbitMQ Cluster - Quorum Queue]
        Node1[Node 1 Leader - Ghi đĩa WAL]
        Node2[Node 2 Follower - Ghi đĩa WAL]
        Node3[Node 3 Follower - Bị sập hoặc Mất điện]

        Node1 -->|Raft Log Replication| Node2
        Node2 -->|Raft Log Replication| Node1
        Node1 -. Mất kết nối .-> Node3
    end

    Exchange[Exchange] -->|Gửi tin nhắn| Node1
    Node1 -->|Đạt đa số 2 trên 3 nodes Commit| Confirm[Gửi Publisher Confirm]
```

---

### Bước 4: Consumer Ack (Xác Nhận Đầu Ra Phía Worker)

* **Vấn đề**: Nếu dùng chế độ xác nhận tự động (`no_ack=True` / Auto-ack), Broker vừa gửi tin nhắn qua socket là lập tức xóa ngay khỏi đĩa. Nếu Worker bị sập nguồn giữa chừng, hết RAM (OOM), hoặc gặp lỗi ngoại lệ, công việc đó sẽ bị mất vĩnh viễn.
* **Bản chất kỹ thuật**:
  * Bắt buộc sử dụng cơ chế xác nhận thủ công (**Manual Acknowledgement** - `no_ack=False`):
    1. Khi Consumer lấy tin nhắn, RabbitMQ chuyển trạng thái của tin nhắn sang `Unacknowledged` (nhưng vẫn giữ nguyên trên đĩa và trong queue).
    2. Worker tiến hành xử lý logic nghiệp vụ nặng.
    3. **Nếu thành công**: Worker phát tín hiệu `basic_ack`. Lúc này RabbitMQ mới chính thức xóa tin nhắn khỏi đĩa.
    4. **Nếu Worker bị sự cố (Crash / Mất điện)**: Socket TCP giữa Worker và RabbitMQ bị đóng $\rightarrow$ RabbitMQ phát hiện kết nối đứt và tự động chuyển trạng thái tin nhắn từ `Unacknowledged` về lại `Ready` (`redelivered=True`) để cấp cho worker khác.
    5. **Nếu lỗi nghiệp vụ (File hỏng)**: Worker phát lệnh `basic_nack(requeue=False)` để đẩy sang Dead Letter Queue.
  * **QoS Fair Dispatch (`prefetch_count=1`)**: Mỗi worker chỉ giữ duy nhất 1 tin nhắn `Unacknowledged`. Xử lý xong mới được cấp tiếp, ngăn ngừa worker bị quá tải.
* **Ý nghĩa**: Chống mất mát dữ liệu **tại đầu ra trong suốt quá trình xử lý (In-processing loss)**.

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': { 'darkMode': true, 'signalTextColor': '#ffffff', 'actorTextColor': '#ffffff', 'signalColor': '#38bdf8', 'lineColor': '#38bdf8' }}}%%
sequenceDiagram
    autonumber
    participant Queue as RabbitMQ Queue
    participant Worker as Worker Process
    participant DB as Database

    Queue->>+Worker: Deliver Message (Đánh dấu Unacknowledged)
    Note over Worker: Worker thực thi nghiệp vụ nặng (Parse PDF, Embeddings, Database writes)
    
    alt Xử lý thành công
        Worker->>DB: Commit dữ liệu
        Worker->>Queue: basic_ack
        Note over Queue: Xóa tin nhắn an toàn khỏi Queue và Đĩa
    else Worker bị crash hoặc mất điện giữa chừng
        Note over Worker: TCP Socket bị đứt đột ngột
        Queue->>Queue: Tự động trả tin nhắn về Queue (redelivered=True)
    else Lỗi nghiệp vụ không thể cứu vãn
        Worker->>Queue: basic_nack (requeue=False)
        Note over Queue: Đẩy sang Dead Letter Queue (DLQ)
    end
    deactivate Worker
```

---

# PHẦN 2: ỨNG DỤNG TOÀN DIỆN VÀO RAG PLATFORM

Dưới đây là cách hệ thống RAG kế thừa nguyên vẹn chu trình 4 bước trên, đồng thời tích hợp thêm các giải pháp chuyên sâu: **JobEnvelope**, **Delayed Retry với TTL**, **Atomic State Gate**, và **SSE Event Streaming**.

---

## 2.1. Bản Đồ Ánh Xạ Kiến Trúc (Architecture Mapping)

| 4 Bước Chuẩn RabbitMQ | Hiện Thực Trong RAG Platform | Mã Nguồn Đại Diện |
|---|---|---|
| **1. Publisher Confirm** | `RabbitMQQueueAdapter` bật `channel.confirm_delivery()`, đóng gói `JobEnvelope` (UUIDv7 `job_id`, `correlation_id`), cờ `delivery_mode=2` (`Persistent`). | [`core/src/core/queue/rabbitmq.py`](file:///c:/Users/ndquynh/Documents/RAG/core/src/core/queue/rabbitmq.py) |
| **2. Routing** | Direct Exchange `rag.direct` định tuyến bằng key `document.ingestion` sang `rag.document.ingestion`. Topic Exchange `rag.events` định tuyến sự kiện SSE theo workspace. | [`core/src/core/queue/rabbitmq.py`](file:///c:/Users/ndquynh/Documents/RAG/core/src/core/queue/rabbitmq.py) |
| **3. Quorum / Durability** | Queue khai báo `durable=True`, cấu hình tham số Quorum hoặc lưu trữ Volume vật lý `rabbitmq_data_prod` gắn vào `/var/lib/rabbitmq`. | [`deploy/docker-compose.prod.yml`](file:///c:/Users/ndquynh/Documents/RAG/deploy/docker-compose.prod.yml) |
| **4. Consumer Ack** | `AsyncRabbitMQConsumer` (`aio-pika`) chạy với `prefetch_count=1`, điều phối qua `JobDispatcher`, chỉ gửi `ack()` sau khi `process_index_document` thành công. | [`core/src/core/queue/consumer.py`](file:///c:/Users/ndquynh/Documents/RAG/core/src/core/queue/consumer.py) |

---

## 2.2. Sơ Đồ Trình Tự Thực Thi Hoàn Chỉnh Của RAG Platform

Sơ đồ mô tả toàn bộ luồng tương tác giữa Người dùng, Web API, Broker RabbitMQ, Cơ chế Retry/DLQ, Worker Ingestion và SSE Hub:

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': { 'darkMode': true, 'signalTextColor': '#ffffff', 'actorTextColor': '#ffffff', 'signalColor': '#38bdf8', 'lineColor': '#38bdf8' }}}%%
sequenceDiagram
    autonumber
    participant Client as Frontend Client
    participant API as chat-api
    participant DB as PostgreSQL pgvector
    participant Producer as RabbitMQ Producer
    participant Broker as RabbitMQ Broker
    participant RetryQ as Retry Queue TTL
    participant DLQ as Dead Letter Queue
    participant Worker as Worker Service
    participant Dispatcher as JobDispatcher
    participant Processor as Index Processor
    participant SSE as SSE Hub

    %% GIAI ĐOẠN 1: BƯỚC 1 & BƯỚC 2 TRONG ẢNH
    rect rgb(15, 43, 72)
    Note over Client,Broker: Giai đoạn 1: Producer Confirm và Routing
    Client->>+API: POST upload document file
    API->>DB: INSERT document queued, ingestion_job queued
    API->>+Producer: enqueue action index
    Note over Producer: Bước 1: Đóng gói JobEnvelope Persistent Mode
    Producer->>Broker: basic_publish exchange rag.direct
    Note over Broker: Bước 2: Direct Exchange định tuyến vào Main Queue
    Note over Broker: Bước 3: Ghi đĩa WAL / Quorum Replication
    Broker-->>Producer: Publisher Confirm ACK (Đã ghi đĩa an toàn)
    Producer-->>-API: Trả về job_id
    API-->>-Client: HTTP 201 Created (status queued)
    end

    %% GIAI ĐOẠN 2: BƯỚC 4 TRONG ẢNH (CONSUMER ACK & XỬ LÝ)
    rect rgb(13, 51, 38)
    Note over Broker,SSE: Giai đoạn 2: Consumer Ack và Xử Lý Idempotent
    Broker->>+Worker: Dispatch 1 job (prefetch=1, Unacknowledged)
    Worker->>Dispatcher: dispatch envelope
    Dispatcher->>+Processor: Gọi hàm xử lý qua thread pool

    %% Tầng bảo vệ Idempotency
    Note over Processor,DB: Kiểm tra Atomic State Gate
    Processor->>DB: UPDATE ingestion_jobs SET status=PROCESSING
    alt rowcount == 0 (Job đang chạy hoặc đã xong)
        Processor-->>Dispatcher: Duplicate detected
        Dispatcher-->>Worker: Skip
        Worker->>Broker: basic_ack xóa tin nhắn trùng
    else rowcount == 1 (Hợp lệ)
        Processor->>SSE: Publish document_progress (10% started)
        SSE-->>Client: SSE Event document_progress (10%)
        
        Note over Processor: Đọc file, Parse PDF, Heading Chunking
        Processor->>SSE: Publish document_progress (50% parsed)
        SSE-->>Client: SSE Event document_progress (50%)
        
        Note over Processor: Gọi Gemini Embeddings (768 dims)
        Processor->>DB: DELETE FROM document_chunks (Clean old chunks)
        Processor->>DB: INSERT vector embeddings
        Processor->>DB: UPDATE documents status=ready, jobs status=completed
        
        Processor->>SSE: Publish document_ready (100%)
        SSE-->>Client: SSE Event document_ready (Hoàn tất)
        Processor-->>Dispatcher: Thành công
        Dispatcher-->>Worker: OK
        Worker->>Broker: basic_ack xác nhận hoàn tất thành công
    end
    deactivate Processor
    deactivate Worker
    end

    %% GIAI ĐOẠN 3: CƠ CHẾ DELAYED RETRY VỚI TTL
    rect rgb(59, 32, 11)
    Note over Worker,RetryQ: Giai đoạn 3: Delayed Retry (TTL và Exponential Backoff)
    opt Khi gặp lỗi tạm thời và retry dưới 3 lần
        Worker->>Worker: Tăng retry_count, tính delay backoff
        Worker->>RetryQ: Publish vào rag.document.ingestion.retry
        Worker->>Broker: basic_ack trên tin nhắn cũ
        Note over RetryQ: Chờ hết thời gian TTL... RabbitMQ tự động DLX
        RetryQ->>Broker: Auto Dead-Letter ngược về Main Queue
    end
    end

    %% GIAI ĐOẠN 4: DEAD LETTER QUEUE KHI VƯỢT QUÁ RETRY
    rect rgb(61, 20, 30)
    Note over Worker,DLQ: Giai đoạn 4: Dead Letter Queue (Cách Ly Sự Cố)
    opt Khi retry từ 3 lần trở lên
        Worker->>DLQ: Chuyển message sang rag.document.ingestion.dlq
        Worker->>DB: UPDATE documents status=failed
        Worker->>SSE: Publish document_failed
        SSE-->>Client: SSE Event document_failed (Báo lỗi)
        Worker->>Broker: basic_ack hoặc basic_reject
    end
    end
```

---

## 2.3. Sơ Đồ Topology Hàng Đợi 3 Tầng Chi Tiết (Topology Flowchart)

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': { 'darkMode': true, 'edgeLabelBackground': '#1e293b' }}}%%
flowchart TD
    API[chat-api - Publisher Confirm Enabled]

    subgraph TANG1 [TẦNG 1: MAIN PROCESSING LAYER]
        DirectEx{Exchange: rag.direct}
        MainQ[Queue: rag.document.ingestion]
    end

    subgraph TANG2 [TẦNG 2: DELAYED RETRY LAYER]
        RetryEx{Exchange: rag.direct.retry}
        RetryQ[Queue: rag.document.ingestion.retry]
    end

    subgraph TANG3 [TẦNG 3: DEAD LETTER LAYER]
        DLX{Exchange: rag.direct.dlx}
        DLQueue[Queue: rag.document.ingestion.dlq]
    end

    Worker[apps/worker - Competing Consumers, Manual ACK]

    %% Routing
    API -->|1. basic_publish delivery_mode=2| DirectEx
    DirectEx -->|routing: document.ingestion| MainQ
    MainQ -->|2. Dispatch 1 job Unacknowledged| Worker

    %% Outcomes
    Worker -->|3a. Xử lý thành công: basic_ack| MainQ
    Worker -->|3b. Thất bại và retry dưới 3 lần: Publish kèm TTL| RetryEx
    RetryEx -->|routing: document.ingestion.retry| RetryQ
    RetryQ -->|4. Hết hạn TTL: Auto DLX về Main Queue| DirectEx

    Worker -->|3c. Thất bại và retry từ 3 lần: Chuyển sang DLQ| DLX
    DLX -->|routing: document.ingestion.dlq| DLQueue
```

---

## 2.4. Sơ Đồ Kiến Trúc Vector Đầy Đủ Của Hệ Thống (Architecture SVG)

![RabbitMQ Architecture](./assets/rabbitmq_architecture.svg)

---

## 2.5. Giải Quyết 4 Bài Toán Vận Hành Trọng Yếu

### 1. Cơ Chế Delayed Retry với TTL (Chống Infinite Loop)
* Không sử dụng `requeue=True` vì sẽ gây ra bão request (thử lại liên tục hàng nghìn lần/giây làm 100% CPU).
* Sử dụng hàng đợi hoãn `rag.document.ingestion.retry`:
  * Message được gán header `expiration = delay_ms`.
  * Khi hết hạn TTL, RabbitMQ tự động đẩy ngược về Main Queue theo cấu hình `x-dead-letter-exchange: rag.direct`.
  * Thời gian chờ tăng theo hàm mũ: Lần 1: 10s, Lần 2: 20s, Lần 3: 40s.

### 2. Chống Trùng Lặp Job (Idempotency) Với 2 Tầng Bảo Vệ
* **Tầng 1 (Database State Gate)**:
  ```sql
  UPDATE ingestion_jobs
     SET status = 'PROCESSING',
         started_at = NOW()
   WHERE id = :job_id
     AND status IN ('PENDING', 'FAILED');
  ```
  Nếu số dòng cập nhật = 0 (job đã xong hoặc worker khác đang xử lý) $\rightarrow$ Worker lập tức gửi `ACK` và bỏ qua (skip).
* **Tầng 2 (Idempotent Writes)**:
  Xóa sạch vector chunk cũ của tài liệu trong PostgreSQL trước khi chèn chunk mới (`DELETE FROM document_chunks WHERE document_id = :doc_id`).

### 3. Scale Ngang Không Trùng Job (Competing Consumers)
* Khi scale worker: `docker compose up -d --scale worker=5`.
* RabbitMQ phân phối message theo thuật toán Round-Robin độc quyền: Mỗi message chỉ được gửi tới **duy nhất 1 channel của 1 worker**.
* Cấu hình `consumer_timeout = 1800s` (30 phút) để tránh trường hợp RabbitMQ hiểu nhầm worker đang bận xử lý tài liệu lớn là bị treo.

### 4. Cam Kết 0% Mất Tin Nhắn Khi Mất Điện (Durability)
1. **Durable Exchange & Queue**: Toàn bộ Exchange và Queue đều được khai báo `durable = True`.
2. **Persistent Message**: Đặt `delivery_mode = 2` (ghi xuống đĩa Write-Ahead Log).
3. **Manual Ack**: Chỉ xóa khỏi đĩa khi có xác nhận thành công từ worker.
4. **Docker Persistent Volume**: Mount thư mục `/var/lib/rabbitmq` ra volume vật lý `rabbitmq_data_prod`. Khi máy chủ khởi động lại, RabbitMQ nạp lại toàn bộ tin nhắn từ ổ cứng.

---

## 2.6. Bảng Tham Số Cấu Hình Hệ Thống

| Tên Biến Môi Trường | Giá Trị Mặc Định | Ý Nghĩa / Mục Đích |
|---|---|---|
| `RABBITMQ_URL` | `amqp://guest:guest@localhost:5672/` | Chuỗi kết nối AMQP tới RabbitMQ Broker |
| `RABBITMQ_EXCHANGE` | `rag.direct` | Tên Direct Exchange chính |
| `RABBITMQ_INGESTION_QUEUE` | `rag.document.ingestion` | Tên hàng đợi chính xử lý Ingestion |
| `RABBITMQ_ROUTING_KEY` | `document.ingestion` | Khóa định tuyến chính |
| `RABBITMQ_PREFETCH_COUNT` | `1` | Số lượng job tối đa cấp cho 1 worker cùng lúc |
| `RABBITMQ_MAX_RETRIES` | `3` | Số lần retry tối đa trước khi đưa vào DLQ |
| `RABBITMQ_INITIAL_RETRY_DELAY_MS` | `10000` | Thời gian chờ cho lần retry đầu tiên (10 giây) |
| `RABBITMQ_EVENTS_EXCHANGE` | `rag.events` | Topic Exchange dành cho sự kiện SSE |

---

## 2.7. Tổ Chức Tệp Mã Nguồn Tương Ứng

```
core/src/core/queue/
├── __init__.py           # Export Ports, Envelopes, Adapters, Dispatcher, Consumer
├── schema.py             # JobEnvelope (UUIDv7, correlation_id, retry_count)
├── port.py               # JobQueuePort & IngestionQueuePort (tương thích ngược 100%)
├── rabbitmq.py           # RabbitMQQueueAdapter (pika, publisher confirms, persistent)
├── in_memory.py          # InMemoryQueueAdapter (phục vụ unit test offline)
├── background.py         # BackgroundQueueAdapter (phục vụ local mock)
└── consumer.py           # JobDispatcher & AsyncRabbitMQConsumer (aio-pika, prefetch=1, DLQ, TTL)

apps/worker/src/worker/
├── main.py               # Bootstrap ứng dụng worker, khởi chạy consumer
└── processors/
    └── index_document.py # Xử lý phân tích PDF, chunking, embedding, atomic state gate
```
