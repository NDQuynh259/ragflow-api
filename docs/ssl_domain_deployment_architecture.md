# Kiến Trúc Triển Khai Tên Miền, Cloudflare Edge & SSL/TLS Cho Hệ Thống RAG

> **Tên Miền Hệ Thống**: `infoflow.asia` / `api.infoflow.asia`  
> **Nhà Đăng Ký (Registrar)**: iNET  
> **Quản Trị DNS & CDN**: Cloudflare Anycast Network  
> **Máy Chủ Dịch Vụ (Origin)**: Production VPS (Ubuntu / Docker Compose)  
> **Phiên Bản Tài Liệu**: 1.0.0  

---

## 1. Sơ Đồ Kiến Trúc Tổng Thể (End-to-End Architecture)

Hệ thống được thiết kế theo mô hình **Edge-to-Origin Proxy**, phân tách rõ ràng giữa tầng rìa mạng (Cloudflare Edge) và máy chủ dịch vụ nội bộ (VPS Origin):

```mermaid
flowchart TD
    subgraph Clients["🌐 Người Dùng & Ứng Dụng Client"]
        Browser["Trình Duyệt Web (https://infoflow.asia)"]
        MobileApp["Mobile / SDK (https://api.infoflow.asia)"]
    end

    subgraph Cloudflare["🛡️ CLOUDFLARE EDGE NETWORK (Anycast DNS)"]
        CF_DNS["Cloudflare DNS (adi.ns / memphis.ns)"]
        CF_SSL["Mã Hóa Universal SSL (TLS 1.2 / TLS 1.3)"]
        CF_WAF["Tường Lửa WAF, Chống DDoS, Rate Limit"]
        CF_Edge["Edge Proxy (IP: 172.67.219.145, 104.21.17.19)"]
    end

    subgraph VPS["🖥️ MÁY CHỦ VPS GỐC (Origin Server)"]
        Firewall["UFW / iptables (Cổng 80, 443)"]
        Nginx["Nginx Reverse Proxy (Container: rag_nginx_prod)"]
        
        subgraph DockerServices["Docker Services (rag_prod_net)"]
            ChatAPI["FastAPI App (:8000)"]
            Worker["Background Worker (Docling / Gemini Vision)"]
            RabbitMQ["RabbitMQ Broker (:5672 / UI :15672)"]
            Postgres["PostgreSQL + pgvector (:5432)"]
        end
    end

    Browser -->|1. HTTPS :443 (Ổ Khóa Xanh)| CF_SSL
    MobileApp -->|1. HTTPS :443 (Ổ Khóa Xanh)| CF_SSL
    CF_SSL --> CF_WAF
    CF_WAF --> CF_Edge
    CF_Edge -->|2. HTTP :80 (Chế độ Flexible)| Firewall
    Firewall --> Nginx
    
    Nginx -->|Proxy HTTP :8000| ChatAPI
    Nginx -->|Proxy UI :15672| RabbitMQ
    ChatAPI -->|Pub/Sub Event| RabbitMQ
    RabbitMQ -->|Trigger Job| Worker
    Worker -->|Lưu Trữ Vector| Postgres
    ChatAPI -->|Truy Vấn Vector| Postgres
```

---

## 2. Luồng Định Tuyến Tên Miền (DNS Delegation)

Tên miền `infoflow.asia` được ủy quyền hoàn toàn từ nhà đăng ký sang Cloudflare:

```text
[Nhà Đăng Ký iNET]
       │
       ▼ (Cập nhật NameServer)
[Nameservers Cloudflare]
       ├── adi.ns.cloudflare.com
       └── memphis.ns.cloudflare.com
```

### Bảng Cấu Hình Bản Ghi DNS Trên Cloudflare:

| Loại (Type) | Tên (Name) | Địa Chỉ Đích (Content) | Trạng Thái Proxy | Mục Đích |
| :--- | :--- | :--- | :--- | :--- |
| **A** | `@` *(hoặc infoflow.asia)* | `<IP_VPS>` | **Proxied ☁️ (Màu cam)** | Web chính `https://infoflow.asia` |
| **A** | `api` | `<IP_VPS>` | **Proxied ☁️ (Màu cam)** | API endpoint `https://api.infoflow.asia` |

> [!NOTE]
> **Quy tắc nhập ô Name trên Cloudflare**: 
> Chỉ nhập ký tự đại diện (`@` cho root domain hoặc `api` cho subdomain). Tuyệt đối **không** gõ thêm đuôi `.infoflow.asia` vào ô Name vì Cloudflare sẽ tự động ghép chuỗi, dẫn đến lỗi subdomain lồng 2 cấp (`api.infoflow.asia.infoflow.asia`) khiến chứng chỉ SSL Wildcard không nhận diện được.

---

## 3. Kiến Trúc Mã Hóa SSL/TLS Hai Chặng

Toàn bộ đường truyền kết nối được chia làm hai chặng độc lập:

```text
[Trình Duyệt] ◄─── Chặng 1: HTTPS (Port 443) ───► [Cloudflare Edge] ◄─── Chặng 2: HTTP (Port 80) ───► [VPS Nginx]
```

### 3.1. Phân Tích Các Chế Độ SSL/TLS Của Cloudflare

| Chế Độ (Mode) | Chặng 1 (Browser ↔ CF) | Chặng 2 (CF ↔ VPS) | Đánh Giá Áp Dụng |
| :--- | :--- | :--- | :--- |
| **Off** | HTTP (Không an toàn) | HTTP | Không dùng. |
| **Flexible** *(Hiện tại)* | **HTTPS (Ổ khóa xanh)** | **HTTP (Cổng 80)** | **Triển khai tức thì**: VPS chỉ cần chạy Nginx cổng 80 chuẩn, không cần tự cài đặt hay gia hạn chứng chỉ trên VPS. |
| **Full** | **HTTPS (Ổ khóa xanh)** | **HTTPS (Cổng 443)** | Yêu cầu VPS phải mở cổng 443 và có chứng chỉ (chấp nhận self-signed). *(Từng gây ra lỗi 521 khi VPS chưa mở cổng 443)*. |
| **Full (Strict)** | **HTTPS (Ổ khóa xanh)** | **HTTPS (Cổng 443 CA)** | Yêu cầu VPS cài chứng chỉ Cloudflare Origin CA (hạn 15 năm). Bảo mật cao nhất cho môi trường ngân hàng/enterprise. |

---

## 4. Giải Mã & Khắc Phục Các Sự Cố Điển Hình (Troubleshooting Log)

### Sự Cố 1: Lỗi "This hostname is not covered by a certificate"
* **Nguyên nhân**: Điền `api.infoflow.asia` vào ô Name trong Cloudflare, hệ thống tự động nối thành `api.infoflow.asia.infoflow.asia` (2 cấp subdomain). Chứng chỉ miễn phí của Cloudflare chỉ bảo vệ 1 cấp (`*.infoflow.asia`).
* **Khắc phục**: Sửa ô Name thành duy nhất chữ `api` hoặc ký tự `@`.

### Sự Cố 2: Lỗi "Not Secure" trên trình duyệt
* **Nguyên nhân**: Truy cập đường dẫn `http://` thay vì `https://`, và Cloudflare chưa bật tự động chuyển hướng.
* **Khắc phục**: 
  1. Truy cập trực tiếp qua tiền tố `https://`.
  2. Bật công tắc **"Always Use HTTPS"** tại mục `SSL/TLS` $\rightarrow$ `Edge Certificates` trên Cloudflare.

### Sự Cố 3: Lỗi "Error 521: Web server is down"
* **Nguyên nhân**: Cloudflare đặt chế độ mã hóa là `Full` (hoặc `Automatic: Full`). Cloudflare gửi request HTTPS tới cổng 443 của VPS, nhưng VPS chỉ mới cấu hình Nginx lắng nghe cổng 80. Kết nối bị từ chối $\implies$ Báo lỗi 521.
* **Khắc phục**: Chuyển chế độ SSL/TLS trên Cloudflare sang **`Flexible`**. Cloudflare sẽ tự động chuyển tiếp request về cổng 80 của VPS, kết nối thành công 100%.

---

## 5. Cấu Hình Nginx Reverse Proxy Trên VPS

Toàn bộ cấu hình Nginx nằm trong thư mục `deploy/nginx/`:

### 5.1. Khôi Phục IP Thật Người Dùng ([cf-real-ip.conf](file:///c:/Users/ndquynh/Documents/RAG/deploy/nginx/snippets/cf-real-ip.conf))
Khi request đi qua Cloudflare Proxy, IP kết nối đến VPS sẽ là IP của Cloudflare. Để log và rate limit nhận diện đúng IP của khách truy cập:
```nginx
# Lấy đúng IP thật từ Header Cloudflare gửi xuống
real_ip_header CF-Connecting-IP;
real_ip_recursive on;
```

### 5.2. Tối Ưu Hóa SSE Streaming Cho Chatbot RAG ([sse-proxy.conf](file:///c:/Users/ndquynh/Documents/RAG/deploy/nginx/snippets/sse-proxy.conf))
API RAG trả lời câu hỏi theo dạng sinh chữ từng token (Server-Sent Events). Nginx cần tắt toàn bộ bộ đệm (buffering) để chữ xuất hiện mượt mà theo thời gian thực:
```nginx
proxy_buffering off;
proxy_cache off;
proxy_set_header Connection '';
proxy_http_version 1.1;
chunked_transfer_encoding on;
proxy_read_timeout 300s;
```

### 5.3. Định Tuyến Ứng Dụng Chính ([rag-api.conf](file:///c:/Users/ndquynh/Documents/RAG/deploy/nginx/conf.d/rag-api.conf))
```nginx
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name infoflow.asia api.infoflow.asia;

    client_max_body_size 100M;
    include /etc/nginx/snippets/cf-real-ip.conf;

    # Healthcheck
    location /nginx-health {
        return 200 "healthy\n";
    }

    # SSE Streaming endpoint (Chat RAG)
    location ~* ^/api/v1/messages/(stream|query) {
        limit_req zone=api_limit burst=15 nodelay;
        proxy_pass http://chat_api_backend;
        include /etc/nginx/snippets/sse-proxy.conf;
    }

    # REST APIs thông thường
    location / {
        limit_req zone=api_limit burst=30 nodelay;
        proxy_pass http://chat_api_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## 6. Lộ Trình Nâng Cấp: Cloudflare Origin CA (Tùy Chọn Enterprise)

Khi cần mã hóa toàn trình 100% (cả chặng Cloudflare $\rightarrow$ VPS) mà không lo gia hạn:
1. Vào Cloudflare $\rightarrow$ **SSL/TLS** $\rightarrow$ **Origin Server** $\rightarrow$ Bấm **Create Certificate**.
2. Chọn thời hạn **15 năm**, copy cặp key:
   * Certificate: `/deploy/nginx/ssl/cert.pem`
   * Private Key: `/deploy/nginx/ssl/key.pem`
3. Thêm block `listen 443 ssl;` vào Nginx và chuyển Cloudflare sang chế độ **`Full (Strict)`**.
