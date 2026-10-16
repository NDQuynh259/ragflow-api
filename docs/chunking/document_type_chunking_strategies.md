# Chiến Lược Chunking Theo Từng Loại Tài Liệu Doanh Nghiệp

Tài liệu này đặc tả toàn diện chiến lược chunking (băm nhỏ văn bản) cho 5 nhóm tài liệu trọng tâm trong hệ thống RAG Enterprise (`NDQuynh259/ragflow-api`). Chiến lược này kết hợp phân tích đặc thù cấu trúc tài liệu thực tế, hành vi xử lý toàn trình từ Ingestion API qua RabbitMQ Worker đến Document Pipeline, và các tham số vận hành có thể kiểm chứng.

> [!IMPORTANT]
> **Nguyên tắc cốt lõi:** Một tài liệu doanh nghiệp hiếm khi đồng nhất 100% về mặt định dạng. Preset cấp tài liệu (`document_type`) đóng vai trò là cấu hình mặc định ban đầu, còn quá trình băm thực tế được điều phối linh hoạt theo từng phần tử (`LayoutElement`) và ranh giới phân cấp (`section_path`).

---

## 1. Luồng Phân Giải Loại Tài Liệu Toàn Trình (End-to-End Type Resolution)

Loại tài liệu (`document_type`) được quản lý xuyên suốt từ tầng giao tiếp người dùng đến worker xử lý nền:

```text
[Client / UI Upload] ──(document_type)──► [apps/chat-api: UploadDocumentCommand]
                                                    │
                                                    ▼
                                          [core/queue: RabbitMQ Queue]
                                          (JobPayload: document_type)
                                                    │
                                                    ▼
                                          [apps/worker: IngestionService]
                                                    │
                                                    ▼
                                    [rag_document_pipeline: DocumentPipeline]
                                                    │
               ┌────────────────────────────────────┴────────────────────────────────────┐
               ▼ (Nếu có explicit_type)                                                  ▼ (Nếu document_type = None)
    Chuẩn hóa Alias qua                                                        Phân loại Heuristic qua
    normalize_document_type()                                                  infer_document_type(elements)
               │                                                                         │
               └────────────────────────────────────┬────────────────────────────────────┘
                                                    ▼
                                          Resolved Document Type
                         ┌──────────────────────────┴──────────────────────────┐
                         ▼                                                     ▼
                "internal" (Mặc định)                           "legal_policy" | "business_plan" |
            chunk_size = 1200 chars                              "progress_report" | "guide_sop"
        threshold_percentile = 80.0                                 chunk_size = 1500 - 2000 chars
          semantic_chunking = True                                     semantic_chunking = False
                                                                (Bảo toàn ranh giới cấu trúc/section)
```

### 1.1. Chuẩn hóa Alias (`normalize_document_type`)
Hệ thống hỗ trợ ánh xạ các tên gọi tương đương từ client/API về 5 profile chuẩn trong [`pipeline.py`](../../packages/rag-document-pipeline/src/rag_document_pipeline/pipeline.py):

| Profile Chuẩn | Alias Hỗ Trợ |
| :--- | :--- |
| `internal` | `internal`, `general_internal` |
| `legal_policy` | `legal`, `policy`, `legal_policy`, `legal-policy` |
| `business_plan` | `business`, `business_plan`, `business-plan` |
| `progress_report` | `progress`, `progress_report`, `progress-report` |
| `guide_sop` | `guide`, `sop`, `guide_sop`, `guide-sop` |

### 1.2. Nhận diện Heuristic & Cơ chế Fallback an toàn
Khi client không cung cấp `document_type`, hàm `infer_document_type()` sẽ quét tần suất các từ khóa đặc trưng trong Heading và Body (Heading được nhân trọng số x2):
* Điểm số phân loại yêu cầu `score >= 3` và không bị hòa điểm ở hạng 1.
* **Cơ chế Fallback:** Nếu không thỏa mãn, hệ thống sẽ fallback về profile `"internal"`.
* **Cảnh báo vận hành:** Khi fallback về `"internal"`, cờ `semantic_chunking` được kích hoạt (`threshold_percentile=80.0`). Cần khuyến khích người dùng/client truyền tường minh `document_type` khi upload qua API để tránh việc văn bản pháp lý hoặc báo cáo tài chính bị cắt vụn ngoài ý muốn do phân loại sai.

---

## 2. Phân Tích Chuyên Sâu 5 Nhóm Tài Liệu Doanh Nghiệp

| Nhóm tài liệu | Cấu trúc văn bản thường gặp | Rủi ro chí tử trong RAG (Tử huyệt) | Chiến lược xử lý đề xuất |
| :--- | :--- | :--- | :--- |
| **1. Tài liệu nội bộ**<br>*(Wiki, cẩm nang, thông báo)* | Văn xuôi theo chủ đề, đề mục H1-H3, bullet points, danh sách việc cần làm. | - Chunk quá ngắn làm đứt mạch ý tưởng.<br>- Chunk quá dài trộn lẫn 2-3 chủ đề khác nhau gây loãng vector representation. | - Bật **Mô hình Lai (Hybrid Semantic)**.<br>- Dùng cửa sổ trượt (Sliding Window) đo khoảng cách ngữ nghĩa giữa các câu; cắt chunk tại điểm nhảy vọt chủ đề (`threshold_percentile=80.0`). |
| **2. Kế hoạch kinh doanh**<br>*(Business Plan, chiến lược, ngân sách)* | Mục tiêu, giả định vĩ mô, bảng dự toán dòng tiền, biểu đồ thị phần, kịch bản rủi ro. | - Số liệu bị tách rời khỏi **đơn vị tính** (triệu USD vs tỷ VND), **kỳ hạn** hoặc **giả định điều kiện**.<br>- Biểu đồ/bảng mất chú thích (caption/footnote). | - **Tắt semantic split** để tránh cắt ngang bảng phân tích/giả định.<br>- Giữ chunk rộng (1500 ký tự) gắn chặt bảng ngân sách với đoạn văn bản dẫn giải liền kề.<br>- Bảo toàn metadata đơn vị và điều kiện. |
| **3. Báo cáo tiến độ**<br>*(Progress/Sprint/KPI Report)* | Kỳ báo cáo (Tuần/Tháng/Quý), mục tiêu cam kết, kết quả thực tế, blocker, next steps. | - Chỉ số KPI bị tách khỏi kỳ đo hoặc người phụ trách.<br>- Trộn lẫn số liệu giữa Quý trước và Quý này do khoảng cách địa lý gần nhau trong cùng trang PDF. | - **Tắt semantic split**; ưu tiên ranh giới section thời gian.<br>- Bắt buộc tiêm (inject) kỳ báo cáo và tên dự án vào metadata/tiêu đề của từng chunk.<br>- Không gom các kỳ báo cáo khác nhau vào cùng một chunk. |
| **4. Điều khoản dịch vụ / Pháp lý**<br>*(ToS, Hợp đồng, Quy chế, Chính sách)* | Phân cấp nghiêm ngặt: `Chương > Mục > Điều > Khoản > Điểm`, định nghĩa pháp lý, ngoại lệ và miễn trừ. | - Cắt ngang mệnh đề điều kiện (`Trừ trường hợp...`) biến ngoại lệ thành quy tắc chung hoặc ngược lại.<br>- Mất tham chiếu chéo (`như quy định tại Khoản 2 Điều 15`). | - **Tuyệt đối không dùng semantic split**.<br>- Cắt cứng theo ranh giới `Điều` hoặc `Khoản`.<br>- Kế thừa toàn bộ breadcrumb `section_path` (ví dụ: `Chương II > Điều 12 > Khoản 3`).<br>- Chunk size lớn (khoảng 2000 ký tự) để chứa trọn vẹn cả quy tắc lẫn ngoại lệ. |
| **5. Tài liệu hướng dẫn**<br>*(SOP, User Guide, Quy trình thao tác)* | Các bước tuần tự (Step 1, Step 2...), lưu ý, cảnh báo (Warning/Danger), ảnh chụp màn hình minh họa. | - Ảnh minh họa bị tách rời khỏi bước thao tác liên quan.<br>- Thứ tự trích xuất trong PDF 2 cột bị đảo lộn, khiến bước sau bị xếp trước bước trước. | - Giữ nguyên thứ tự tuần tự của các bước.<br>- Nhóm đoạn hướng dẫn, ghi chú cảnh báo và ảnh chụp màn hình trong cùng một ngữ cảnh cục bộ.<br>- Bảo toàn metadata chỉ dẫn thao tác. |

---

## 3. Tham Số Cấu Hình & Quy Đổi Token Tiếng Việt Thực Tế

Trong hệ thống RAG xử lý văn bản tiếng Việt, việc cấu hình độ dài theo **số ký tự** cần được tính toán quy đổi cẩn trọng với **số lượng Token** thực tế của các mô hình nhúng (Embedding Models). 

Do đặc thù ngôn ngữ có dấu thanh và từ ghép, các BPE/WordPiece Tokenizer phổ biến (như OpenAI `cl100k_base`, `bge-m3`, `multilingual-e5`) thường tách 1 từ tiếng Việt thành 1.2 – 1.8 tokens (khoảng 2.8 – 3.8 ký tự / token).

### 3.1. Bảng Thông Số Khởi Đầu & Dự Toán Token

| Profile | Chunk Size (Ký tự) | Dự toán Tokens (Tiếng Việt) | Semantic Split | Ngưỡng Percentile | Mô hình Embedding phù hợp |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **`internal`** | `1200` | ~ 320 – 420 | **Bật** | `80.0` | `bge-m3` (8k), `text-embedding-3` (8k), `e5-base` (512) |
| **`business_plan`** | `1500` | ~ 400 – 520 | Tắt | N/A | `bge-m3`, `text-embedding-3` (Khuyến nghị context ≥ 1024) |
| **`progress_report`** | `1500` | ~ 400 – 520 | Tắt | N/A | `bge-m3`, `text-embedding-3` |
| **`legal_policy`** | `2000` | ~ 550 – 720 | Tắt | N/A | `bge-m3`, `text-embedding-3` (Cần context > 512 tokens) |
| **`guide_sop`** | `1500` | ~ 400 – 520 | Tắt | N/A | `bge-m3`, `text-embedding-3` |

> [!WARNING]
> Nếu dự án sử dụng mô hình embedding có giới hạn cứng ngữ cảnh là **512 tokens** (như một số biến thể MiniLM hoặc multilingual-e5 cũ), cấu hình `legal_policy` (2000 ký tự ~ 720 tokens) sẽ bị **cắt cụt phần đuôi** (truncation), dẫn đến việc mất các điều khoản ngoại lệ ở cuối chunk. Trong trường hợp đó, bắt buộc phải hạ `chunk_size` xuống `1200` ký tự hoặc chuyển sang embedding model hỗ trợ 8192 tokens.

---

## 4. Xử Lý Bảng Biểu, Hình Ảnh & Đa Phương Thức

Quan hệ giữa bảng, biểu đồ, hình ảnh và văn bản xung quanh phải tuân thủ nguyên tắc đa tầng tín hiệu, không dựa thuần túy vào thứ tự xuất hiện trên trang PDF:

### 4.1. Bảng biểu (`TableChunker`)
* **Repeated Header:** Với các bảng dài chia nhỏ thành nhiều sub-chunks, hàng tiêu đề (Markdown table header) luôn được lặp lại tự động ở đầu mỗi chunk con để đảm bảo mô hình embedding hiểu được ý nghĩa các cột ở các dòng bên dưới.
* **Oversized Row Handling:** Các dòng bảng có nội dung quá dài (chứa danh sách kiểm tra hoặc đoạn văn dài trong một ô) được phân tách có kiểm soát mà không làm vỡ cấu trúc Markdown.
* **Row-wise Key-Value Proxy:** Khi cần lập chỉ mục vector, bảng có thể sinh ra văn bản biểu diễn dạng `Cột A = Giá trị A | Cột B = Giá trị B` để tăng độ chính xác truy hồi ngữ nghĩa.

### 4.2. Hình ảnh & Biểu đồ (`ImageChunker`)
* **Image Triage (Bộ lọc rác):** Loại bỏ tự động các ảnh trang trí, icon, thanh phân cách dựa trên kích thước (`min_image_size=100px`) và tỷ lệ khung hình (`max_aspect_ratio=5.0`).
* **VLM Vision Callback (`vision_fn`):** Các sơ đồ quy trình trong tài liệu SOP hoặc biểu đồ tài chính trong Business Plan được định tuyến đến mô hình Vision (VLM) để sinh văn bản mô tả cấu trúc, chú giải số liệu và gắn nhãn trước khi index.
* **Bảo toàn Captions & Footnotes:** [`LayoutNormalizer`](../../packages/rag-document-pipeline/src/rag_document_pipeline/normalizers/layout.py) gắn các caption/footnote đứng rời vào bảng hoặc hình ảnh lân cận nếu chúng thuộc cùng trang và có tín hiệu định dạng tương ứng.

---

## 5. Hiện Trạng Triển Khai & Khuyến Nghị Tối Ưu Codebase

Bảng đối chiếu giữa tài liệu chiến lược và các module mã nguồn trong [`packages/rag-document-pipeline`](../../packages/rag-document-pipeline):

| Module Code | Tác vụ đã xác nhận trong mã nguồn | Giới hạn thực tế & Đề xuất cải tiến |
| :--- | :--- | :--- |
| [`pipeline.py`](../../packages/rag-document-pipeline/src/rag_document_pipeline/pipeline.py) | - `normalize_document_type()` chuẩn hóa alias.<br>- `infer_document_type()` nhận diện heuristic từ heading/text.<br>- Điều phối `CHUNKING_PROFILES` gắn cờ `semantic_enabled` và `chunk_size`. | **Cải tiến:** Nên bổ sung log cảnh báo khi `infer_document_type` fallback về `"internal"`. Cho phép cấu hình ghi đè tham số qua biến môi trường. |
| [`normalizers/layout.py`](../../packages/rag-document-pipeline/src/rag_document_pipeline/normalizers/layout.py) | - Gắn kết tự động caption và footnote cùng trang vào phần tử bảng / ảnh liền kề. | **Cải tiến:** Parser PDF hai cột có thể làm lệch thứ tự phần tử; cần kiểm tra tọa độ bounding box (`bbox`) khi có thông tin hình học từ parser. |
| [`chunking/core/section.py`](../../packages/rag-document-pipeline/src/rag_document_pipeline/chunking/core/section.py) | - `propagate_sections()` lan truyền đường dẫn phân cấp `section_path` theo các thẻ `heading`. | **Hạn chế pháp lý:** Các dòng văn bản như `Điều 12.`, `Khoản 3.` thường bị PDF parser trích xuất thành `paragraph` thông thường chứ không thành `heading`. Cần thêm một bước tiền xử lý nhận diện Regex để chuyển đổi các điểm mục pháp lý thành `heading`. |
| [`chunking/strategies/text.py`](../../packages/rag-document-pipeline/src/rag_document_pipeline/chunking/strategies/text.py) | - Mô hình Lai: phân tách câu tiếng Việt, Sliding Window, cosine distance và phát hiện topic shift qua `threshold_percentile`. | **Đã tối ưu:** Cờ `semantic_enabled=False` cho phép tắt hoàn toàn topic shift cho các nhóm tài liệu có cấu trúc định sẵn (Legal, Report, Business, SOP). |
| [`chunking/multimodal.py`](../../packages/rag-document-pipeline/src/rag_document_pipeline/chunking/multimodal.py) | - Router điều phối luồng văn bản, bảng biểu, hình ảnh; giải quyết liên kết tham chiếu đánh số khi đích phân giải duy nhất. | **Đã tối ưu:** Bảo toàn reading order tổng thể và flush batch văn bản trước khi chunk từng modality độc lập. |

---

## 6. Đặc Tả Chuẩn Metadata Đầu Ra (Chunk Metadata Contract)

Mỗi chunk được tạo ra từ pipeline mang theo metadata chuẩn hóa để hỗ trợ cả truy hồi Vector và lọc thuộc tính (FTS / Hybrid Search) trên cơ sở dữ liệu:

```json
{
  "chunk_id": "chunk_7f2b9a8c",
  "document_id": "doc_12345678",
  "document_type": "legal_policy",
  "chunk_size_chars": 1842,
  "semantic_chunking": false,
  "page_span": [4, 5],
  "section_path": [
    "Chương II: Nghĩa Vụ Của Bên Cung Cấp",
    "Điều 8: Cam Kết Chất Lượng Dịch Vụ (SLA)"
  ],
  "modality": "text",
  "table_metadata": null,
  "image_metadata": null,
  "cross_references": [
    "Điều 12",
    "Phụ lục A"
  ]
}
```

* **`document_type`:** Xác định danh mục tài liệu phục vụ việc phân loại và bộ lọc tìm kiếm.
* **`section_path`:** Đường dẫn breadcrumb giúp mô hình LLM xác định vị trí ngữ cảnh trong tài liệu gốc.
* **`semantic_chunking`:** Ghi nhận xem chunk được sinh ra theo thuật toán ngữ nghĩa hay theo ranh giới cấu trúc.
* **`cross_references`:** Danh sách các điều khoản/phụ lục được tham chiếu trực tiếp trong nội dung chunk.

---

## 7. Khung Đánh Giá & Tinh Chỉnh Tham Số (Evaluation & Benchmarking)

Không đưa cấu hình vào môi trường production chỉ dựa trên cảm quan. Cần xây dựng tập kiểm thử chuẩn (Golden Evaluation Dataset) với ít nhất 100 câu truy vấn đại diện cho 5 nhóm tài liệu:

```text
                               ┌──────────────────────────────────────────────┐
                               │           Tập Đánh Giá Độc Lập               │
                               │  (20 câu hỏi đại diện / nhóm tài liệu)       │
                               └──────────────────────┬───────────────────────┘
                                                      │
                       ┌──────────────────────────────┴──────────────────────────────┐
                       ▼                                                             ▼
           [Chỉ Số Truy Hồi - Retrieval]                                 [Chỉ Số Thế Hệ - Generation]
           - Recall@k (k=3, 5): Đo khả năng bao quát                  - Faithfulness (Ragas): Tránh ảo giác số liệu
           - MRR (Mean Reciprocal Rank): Độ ưu tiên                   - Context Relevance: Mức độ sạch ngữ cảnh
           - Precision@k: Tỷ lệ chunk thực sự có ích                  - Answer Relevance: Trả lời đúng trọng tâm
```

### 7.1. Bộ tiêu chí kiểm định theo loại tài liệu

1. **Văn bản pháp lý (`legal_policy`):**
   * *Kiểm tra:* Khi hỏi về một ngoại lệ hoặc mức phạt, chunk trả về có bao gồm trọn vẹn mệnh đề "trừ trường hợp..." hay không?
   * *Tiêu chí đạt:* 100% các câu hỏi về điều kiện không bị đứt đoạn giữa chừng.
2. **Kế hoạch kinh doanh & Ngân sách (`business_plan`):**
   * *Kiểm tra:* Số liệu tài chính trích xuất có đi kèm đơn vị tính và ghi chú điều kiện (ví dụ: "chưa bao gồm VAT", "triệu USD") không?
   * *Tiêu chí đạt:* Không có câu trả lời nào của LLM nhầm lẫn giữa USD và VND.
3. **Báo cáo tiến độ (`progress_report`):**
   * *Kiểm tra:* Câu hỏi so sánh giữa Sprint 1 và Sprint 2 có truy hồi đúng chunk của từng Sprint tương ứng không?
   * *Tiêu chí đạt:* Tách biệt rạch ròi trạng thái hoàn thành giữa các kỳ đo.
4. **Tài liệu hướng dẫn (`guide_sop`):**
   * *Kiểm tra:* Quy trình thao tác có bảo toàn đúng thứ tự các bước từ 1 đến N và gắn đúng hình ảnh minh họa không?
   * *Tiêu chí đạt:* Không xảy ra tình trạng hình ảnh của Bước 3 bị gán nhầm vào Bước 1.

---

> [!TIP]
> **Tổng kết:** Một hệ thống RAG Enterprise hiệu quả không phải là hệ thống dùng chung một công thức chunking cho tất cả, mà là hệ thống biết **khi nào cần tôn trọng cấu trúc tự nhiên (Pháp lý, Báo cáo, Quy trình)** và **khi nào cần áp dụng AI đo khoảng cách ngữ nghĩa (Nội dung văn xuôi, Wiki nội bộ)**. Việc thiết lập preset theo 5 nhóm tài liệu kết hợp giám sát chặt chẽ tỷ lệ token thực tế là nền móng bảo đảm chất lượng truy hồi cao nhất.
