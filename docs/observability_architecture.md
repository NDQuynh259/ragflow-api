# KIẾN TRÚC LOGGING, MONITORING & OBSERVABILITY (HỆ THỐNG RAG)
> **Chiến lược: Open-Source Stack (Không phụ thuộc AWS CloudWatch)**  
> **Các trụ cột cốt lõi**: Structured Logging (Loki), Metrics (Prometheus), Distributed Tracing (Tempo), LLMOps Tracing (Langfuse), Trực quan hóa & Cảnh báo (Grafana).

---

## 1. Bối cảnh & Lý do không sử dụng CloudWatch

Mặc dù AWS CloudWatch phổ biến trên nền tảng AWS, việc sử dụng CloudWatch trong thực tế gặp nhiều hạn chế:
1. **Chi phí cao & Khó dự đoán**: CloudWatch tính phí rất đắt theo dung lượng Log Ingestion ($0.50/GB), Metric API Calls (`PutMetricData`), và Custom Metrics. Khi quy mô log và request tăng, hóa đơn CloudWatch có thể chiếm tỷ trọng lớn trong chi phí hạ tầng.
2. **Vendor Lock-in**: Trói chặt ứng dụng vào hệ sinh thái AWS, gây khó khăn khi cần chạy On-premise, Hybrid Cloud, VPS (Hetzner, OVH, DigitalOcean) hoặc Local Development.
3. **Trải nghiệm rời rạc (Siloed Experience)**: CloudWatch Logs Insights, Metrics Dashboards và X-Ray Tracing là các sản phẩm rời rạc, khó liên kết chéo (nhấp từ 1 dòng log lỗi nhảy sang đúng trace span tương ứng).
4. **Không tối ưu cho hệ thống AI / RAG**: CloudWatch không hiểu ngữ cảnh prompt, embedding tokens, chi phí model LLM hay độ tương đồng ngữ nghĩa của các chunk được retrieve.

**Giải pháp thay thế tiêu chuẩn công nghiệp**: Bộ **Grafana LGTM Stack (Loki + Grafana + Tempo + Mimir/Prometheus)** kết hợp với **Langfuse (Self-hosted)** cho tầng AI/RAG.

---

## 2. Kiến trúc Tổng thể (High-Level Architecture)

```mermaid
flowchart TD
    subgraph TierApp ["1. TẦNG ỨNG DỤNG RAG"]
        API["apps/chat-api (FastAPI)"]
        WORKER["apps/worker (Ingestion & Parsing)"]
        SCHED["apps/scheduler (Background Cron)"]
    end

    subgraph TierCollect ["2. TẦNG THU THẬP TELEMETRY"]
        FLUENTBIT["Fluent Bit / Promtail (Gom log stdout)"]
        PROM_CLIENT["Prometheus Client (/metrics)"]
        OTEL_SDK["OpenTelemetry SDK (Trace Context)"]
        LANGFUSE_SDK["Langfuse SDK (Prompt & Token Decorators)"]
    end

    subgraph TierStore ["3. TẦNG LƯU TRỮ & XỬ LÝ (OSS ENGINES)"]
        LOKI[("Grafana Loki (Lưu trữ Log)")]
        PROM[("Prometheus (Lưu trữ Metric)")]
        TEMPO[("Grafana Tempo (Lưu trữ Trace)")]
        LANGFUSE_SRV[("Langfuse Server (LLM Tracing)")]
    end

    subgraph TierUI ["4. TẦNG QUẢN LÝ & CẢNH BÁO"]
        GRAFANA["Grafana Unified Dashboard (Logs + Metrics + Traces)"]
        ALERTING["Grafana Alertmanager"]
        NOTIF["Kênh Cảnh Báo (Telegram / Slack / PagerDuty)"]
    end

    TierApp -->|"Log JSON ra stdout"| FLUENTBIT
    FLUENTBIT -->|"Đẩy log chunks"| LOKI

    TierApp -->|"Expose /metrics"| PROM_CLIENT
    PROM_CLIENT -->|"Scrape định kỳ 15s"| PROM

    TierApp -->|"Inject trace_id"| OTEL_SDK
    OTEL_SDK -->|"OTLP gRPC (Port 4317)"| TEMPO

    TierApp -->|"Trace Prompt & Tokens"| LANGFUSE_SDK
    LANGFUSE_SDK -->|"HTTP Async Batch"| LANGFUSE_SRV

    LOKI --> GRAFANA
    PROM --> GRAFANA
    TEMPO --> GRAFANA

    GRAFANA --> ALERTING
    ALERTING --> NOTIF
```

---

## 3. Trụ cột 1: Structured Logging (Grafana Loki)

### 3.1. Cơ chế hoạt động của Loki
Khác với Elasticsearch đánh index toàn bộ text khiến tốn RAM và đĩa, **Loki chỉ đánh index các labels** (metadata):
- `app`: `chat-api`, `worker`, `scheduler`
- `env`: `production`, `staging`, `development`
- `level`: `INFO`, `ERROR`, `WARNING`

Dữ liệu log được nén thành các chunk nhị phân và lưu thẳng vào ổ đĩa hoặc Object Storage (MinIO / S3) với chi phí cực thấp.

### 3.2. Tiêu chuẩn Log JSON trên Production
Tuân thủ chuẩn **12-Factor App**, toàn bộ dịch vụ xuất log ra `stdout` theo định dạng JSON có cấu trúc:

```json
{
  "timestamp": "2026-10-19T09:25:31.452Z",
  "level": "INFO",
  "logger": "apps.worker.handlers.index_document",
  "service": "rag-worker",
  "env": "production",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "correlation_id": "01a0e655-7dfe-7e80-a70c-4c7617f53dc3",
  "document_id": "doc_99182",
  "chunk_count": 42,
  "duration_ms": 1420.5,
  "message": "Successfully indexed chunks into vector database"
}
```

### 3.3. Thu gom log với Fluent Bit
File cấu hình `fluent-bit.conf` cào log từ Docker container và gửi trực tiếp sang Loki:

```ini
[SERVICE]
    Flush        1
    Daemon       Off
    Log_Level    info

[INPUT]
    Name         forward
    Listen       0.0.0.0
    Port         24224

[FILTER]
    Name         parser
    Match        *
    Key_Name     log
    Parser       json_parser
    Reserve_Data On

[OUTPUT]
    Name         loki
    Match        *
    Host         loki
    Port         3100
    Labels       job=fluentbit, service=$service, env=$env
    Remove_Keys  container_id, container_name
```

---

## 4. Trụ cột 2: Metrics & System Monitoring (Prometheus)

### 4.1. 4 Tín hiệu vàng (Google SRE 4 Golden Signals)

| Tín hiệu | Định nghĩa | Metric thực tế trong RAG System |
| :--- | :--- | :--- |
| **Latency** | Thời gian phản hồi request | `http_request_duration_seconds{quantile="0.95"}` (p95 latency) |
| **Traffic** | Nhu cầu hệ thống | `http_requests_total` (RPS / QPS vào API) |
| **Errors** | Tỉ lệ request bị lỗi | Số lượng HTTP status `5xx`, RabbitMQ message reject / dead-letter |
| **Saturation** | Mức độ quá tải tài nguyên | % CPU/RAM của Worker khi parse PDF, Postgres Connection Pool usage |

### 4.2. Triển khai trong FastAPI (`apps/chat-api`)
Sử dụng thư viện `prometheus-fastapi-instrumentator`:

```python
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI(title="RAG Chat API")

# Tự động xuất các metrics: HTTP latency, request count, response size...
Instrumentator().instrument(app).expose(app, endpoint="/metrics")
```

### 4.3. Giám sát hạ tầng phần cứng & Container
* **cAdvisor**: Giám sát tài nguyên từng Docker Container (% CPU, Memory limit, Network IO, Block IO).
* **Node Exporter**: Giám sát phần cứng máy chủ (Dung lượng ổ đĩa, RAM hệ thống, Tải CPU).

---

## 5. Trụ cột 3: Distributed Tracing (OpenTelemetry + Grafana Tempo)

### 5.1. Vấn đề giải quyết
Một yêu cầu người dùng gửi đến hệ thống RAG trải qua nhiều chặng:
1. `chat-api`: Nhận câu hỏi, kiểm tra quyền.
2. `core/retrieval`: Tạo embedding câu hỏi (gọi Gemini/OpenAI Embedding).
3. `PostgreSQL (pgvector)`: Truy vấn tương đồng cosine top 5 chunks.
4. `core/reranker`: Re-rank lại kết quả.
5. `LLM Generation`: Gọi Gemini 1.5 Pro stream câu trả lời về client.

Nếu tổng thời gian mất **4.2 giây**, Tracing cung cấp biểu đồ thác nước (Waterfall Graph) cho biết chính xác từng chặng mất bao nhiêu mili-giây:

```
[Trace: Query "Quy trình xin nghỉ phép"] -------------------> Total: 4.2s
  ├── [Span] Auth & RateLimit (chat-api): 12ms
  ├── [Span] Gemini Embedding API: 110ms
  ├── [Span] PostgreSQL Vector Search: 85ms
  ├── [Span] Cross-Encoder Rerank: 220ms
  └── [Span] Gemini Stream Generation: 3773ms  <-- Thủ phạm chính
```

### 5.2. Đồng bộ Trace Context qua RabbitMQ (Worker Async)
Khi đẩy job từ API sang Worker qua RabbitMQ, hệ thống tự động inject `traceparent` (chuẩn W3C TraceContext) vào AMQP Message Headers. Khi Worker nhận message, nó trích xuất header này để tiếp tục span cha, giúp trace không bị đứt đoạn giữa các tiến trình độc lập.

---

## 6. Trụ cột 4: AI & LLM Observability (Langfuse Integration)

Các hệ thống APM truyền thống (kể cả CloudWatch hay Datadog) đều **khiếm khuyết** khi quan sát ứng dụng Generative AI / RAG. **Langfuse** được tích hợp chuyên biệt để giải quyết:

```mermaid
flowchart LR
    QUERY["Câu hỏi User"] --> RETRIEVAL["Langfuse Span: Retrieval<br/>• Top K chunks<br/>• Cosine similarity score<br/>• Token context size"]
    RETRIEVAL --> PROMPT["Langfuse Generation: LLM<br/>• System Prompt version<br/>• Input / Output tokens ($)<br/>• Latency (Time to First Token)"]
    PROMPT --> EVAL["Langfuse Evaluation<br/>• Groundedness check<br/>• Relevance Score<br/>• Feedback (Thumbs Up/Down)"]
```

### Cách tích hợp bằng Decorator trong Python:
```python
from langfuse.decorators import observe, langfuse_context

@observe(as_type="generation")
def call_llm_model(prompt: str, context: str):
    # Cập nhật metadata token và chi phí
    langfuse_context.update_current_observation(
        model="gemini-1.5-flash",
        model_parameters={"temperature": 0.2},
    )
    response = gemini_client.generate(prompt, context)
    return response
```

---

## 7. Cảnh báo & Vận hành Sự cố (Alerting Rules)

Toàn bộ luật cảnh báo được định nghĩa tập trung trên **Grafana Alerting**, bắn thông báo trực tiếp qua **Telegram Bot** hoặc **Slack Webhook**:

```yaml
groups:
  - name: rag_system_alerts
    rules:
      # 1. Cảnh báo lỗi 5xx tăng vọt
      - alert: HighHttp5xxRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) * 100 > 5
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Tỉ lệ lỗi 5xx vượt quá 5% trong 2 phút qua"

      # 2. Cảnh báo độ trễ p95 quá cao
      - alert: HighLatencyP95
        expr: histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le)) > 3.0
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Độ trễ p95 vượt quá 3 giây (đang quá tải hoặc API ngoài chậm)"

      # 3. Cảnh báo nghẽn hàng đợi Ingestion (RabbitMQ Backlog)
      - alert: RabbitMQQueueBacklog
        expr: rabbitmq_queue_messages_ready{queue="document.ingestion"} > 100
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Hàng đợi tài liệu còn hơn 100 message chưa được Worker xử lý"
```

---

## 8. Cấu hình Hạ tầng Tham chiếu (`docker-compose.monitoring.yml`)

Dưới đây là file Docker Compose hoàn chỉnh để triển khai toàn bộ cụm Monitoring & Observability độc lập, sẵn sàng chạy cùng cụm ứng dụng RAG:

```yaml
version: "3.8"

networks:
  rag-network:
    external: true

volumes:
  prometheus_data:
  grafana_data:
  loki_data:
  tempo_data:

services:
  # 1. Metrics Storage
  prometheus:
    image: prom/prometheus:v2.51.0
    container_name: rag-prometheus
    restart: unless-stopped
    command:
      - "--config.file=/etc/prometheus/prometheus.yml"
      - "--storage.tsdb.path=/prometheus"
      - "--storage.tsdb.retention.time=15d"
    ports:
      - "9090:9090"
    volumes:
      - ./infra/monitoring/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus_data:/prometheus
    networks:
      - rag-network

  # 2. Logs Storage
  loki:
    image: grafana/loki:3.0.0
    container_name: rag-loki
    restart: unless-stopped
    ports:
      - "3100:3100"
    command: -config.file=/etc/loki/local-config.yaml
    volumes:
      - loki_data:/loki
    networks:
      - rag-network

  # 3. Distributed Tracing Storage
  tempo:
    image: grafana/tempo:2.4.1
    container_name: rag-tempo
    restart: unless-stopped
    command: [ "-config.file=/etc/tempo.yaml" ]
    volumes:
      - ./infra/monitoring/tempo.yaml:/etc/tempo.yaml:ro
      - tempo_data:/var/tempo
    ports:
      - "4317:4317" # OTLP gRPC
      - "3200:3200" # Tempo HTTP
    networks:
      - rag-network

  # 4. Giao diện trực quan hóa chung (Dashboard)
  grafana:
    image: grafana/grafana:10.4.1
    container_name: rag-grafana
    restart: unless-stopped
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_USER=admin
      - GF_SECURITY_ADMIN_PASSWORD=admin_strong_password
      - GF_USERS_ALLOW_SIGN_UP=false
    volumes:
      - grafana_data:/var/lib/grafana
      - ./infra/monitoring/grafana-datasources.yaml:/etc/grafana/provisioning/datasources/datasources.yaml:ro
    depends_on:
      - prometheus
      - loki
      - tempo
    networks:
      - rag-network

  # 5. LLMOps Tracing chuyên biệt cho AI / RAG
  langfuse:
    image: ghcr.io/langfuse/langfuse:2
    container_name: rag-langfuse
    restart: unless-stopped
    ports:
      - "3001:3000"
    environment:
      - NODE_ENV=production
      - DATABASE_URL=postgresql://postgres:postgres@postgres:5432/langfuse
      - NEXTAUTH_SECRET=langfuse_secret_key_change_in_production
      - NEXTAUTH_URL=http://localhost:3001
      - TELEMETRY_ENABLED=false
    networks:
      - rag-network
```

---

## 9. Ma trận So sánh & Tổng kết

| Tiêu chí | AWS CloudWatch Native | Giải pháp Đề xuất (Grafana LGTM + Langfuse) |
| :--- | :--- | :--- |
| **Chi phí bản quyền / License** | Đắt theo traffic & số lượng metrics/logs | **$0** (100% Open Source tự host) |
| **Tính độc lập nhà cung cấp** | Bị khóa chặt vào AWS | Chạy được trên mọi hạ tầng (Docker, K8s, Bare-metal, VPS) |
| **Khả năng liên kết chéo** | Logs, Metrics, Traces nằm ở các màn hình riêng | **Click 1 nút từ Log lỗi nhảy ngay sang Trace waterfall** |
| **Khả năng quan sát LLM/RAG** | Kém (chỉ log chuỗi text thô) | **Rất mạnh**: Theo dõi prompt, version, tokens, chi phí USD, độ liên quan chunk |
| **Tài nguyên vận hành** | Do AWS quản lý | Cần cấu hình lưu trữ đĩa (15-30 ngày retention) và container nhẹ |
