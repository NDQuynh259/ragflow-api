# Kiến trúc Adaptive Multimodal RAG với Structure-Aware Chunking

> Mục tiêu: thiết kế pipeline RAG cho tài liệu có cấu trúc đa dạng như
> SOP/user guide, hợp đồng/chính sách, báo cáo KPI, business plan và
> wiki nội bộ; hỗ trợ PDF nhiều cột, bảng, hình ảnh, biểu đồ và văn bản.

## 1. Mục tiêu thiết kế

-   **Parse trước, chunk sau**: xác định bố cục, thứ tự đọc và loại phần
    tử trước khi chia chunk.
-   **Chunking thích ứng theo loại tài liệu**: không áp dụng một chiến
    lược cố định cho mọi tài liệu.
-   **Xử lý riêng từng loại phần tử**: text, table, image và chart có
    pipeline riêng, sau đó liên kết bằng metadata.
-   **Giữ ngữ cảnh**: lưu breadcrumb tiêu đề, trang, phiên bản, thời
    gian, đơn vị, chú thích và quan hệ cha-con.
-   **Hybrid retrieval**: kết hợp dense vector search, BM25, metadata
    filter và reranking.
-   **Truy vết được**: kết quả truy xuất phải dẫn về tài liệu nguồn,
    trang và phần tử gốc.

## 2. Sơ đồ kiến trúc tổng thể

``` mermaid
flowchart TD
    A[Document Sources<br/>PDF / DOCX / HTML / Wiki / XLSX] --> B[Ingestion API]
    B --> C[Queue / Job Orchestrator]
    C --> D[Document Parser & Layout Analyzer]
    D --> E[Normalized Document IR]
    E --> F[Document Type Classifier]
    F --> G[Adaptive Chunking Router]

    G --> H1[SOP / Procedure Chunker]
    G --> H2[Legal Hierarchy Chunker]
    G --> H3[Report / KPI Chunker]
    G --> H4[Business Plan Chunker]
    G --> H5[Wiki / Semantic Chunker]

    E --> I[Element Processors]
    I --> I1[Text / OCR]
    I --> I2[Table Processor]
    I --> I3[Image Caption / Vision]
    I --> I4[Chart Data Extractor]

    H1 --> J[Context Enrichment & Relationships]
    H2 --> J
    H3 --> J
    H4 --> J
    H5 --> J
    I1 --> J
    I2 --> J
    I3 --> J
    I4 --> J

    J --> K[Chunk Validation & Deduplication]
    K --> L[Embedding Service]
    L --> M[(Vector Index)]
    K --> N[(Document / Metadata Store)]
    K --> O[(Object Storage: originals, images)]

    Q[User Query] --> R[Query Understanding]
    R --> S[Metadata Filter]
    S --> T[Hybrid Retrieval: Vector + BM25]
    M --> T
    N --> T
    T --> U[Reranker]
    U --> V[Parent / Related-Element Expansion]
    V --> W[Context Builder]
    W --> X[LLM Answer + Source Citations]
```

### Vai trò các thành phần

  -----------------------------------------------------------------------
  Thành phần                          Trách nhiệm
  ----------------------------------- -----------------------------------
  Ingestion API                       Nhận file, xác thực, lưu trạng thái
                                      và tạo job

  Queue / Orchestrator                Chạy xử lý nền, retry, theo dõi lỗi
                                      và giới hạn concurrency

  Parser & Layout Analyzer            Trích xuất text, bảng, ảnh, thứ tự
                                      đọc, tiêu đề và bounding boxes

  Normalized Document IR              Biểu diễn thống nhất các phần tử đã
                                      parse

  Type Classifier                     Phân loại tài liệu hoặc từng
                                      section theo loại nội dung

  Adaptive Chunking Router            Chọn chiến lược chunking phù hợp

  Element Processors                  Chuẩn hóa bảng, OCR/vision cho ảnh
                                      và trích xuất dữ liệu biểu đồ

  Context Enrichment                  Bổ sung breadcrumb, metadata và
                                      quan hệ giữa chunk

  Embedding Service                   Tạo vector embedding cho nội dung
                                      phù hợp

  Vector / Metadata Store             Lưu vector, nội dung chunk,
                                      metadata và quan hệ

  Retrieval Pipeline                  Lọc metadata, hybrid search, rerank
                                      và mở rộng ngữ cảnh

  Context Builder                     Ghép các chunk liên quan mà không
                                      làm mất nguồn gốc

  LLM Answer                          Sinh câu trả lời dựa trên context,
                                      kèm trích dẫn nguồn
  -----------------------------------------------------------------------

## 3. Pipeline ingestion chi tiết

### Bước 1 --- Nhận và lưu tài liệu

1.  Nhận file cùng metadata ban đầu: tenant/workspace, người tải lên,
    quyền truy cập, loại file.
2.  Tạo `document_id`, `version_id` và job ID.
3.  Lưu file gốc vào object storage.
4.  Đưa job vào queue để xử lý nền.
5.  Kiểm tra MIME type, kích thước, checksum và trạng thái xử lý.

Trạng thái đề xuất: `QUEUED`, `PARSING`, `CLASSIFYING`, `CHUNKING`,
`EMBEDDING`, `INDEXED`, `FAILED`.

### Bước 2 --- Parse và phân tích layout

Với PDF phức tạp, không nên bắt đầu bằng cách lấy toàn bộ text rồi chia
theo số ký tự. Hãy dùng parser có khả năng nhận biết layout, thứ tự đọc
và phần tử tài liệu.

Các lựa chọn có thể đánh giá: - **Docling**: phù hợp để thử nghiệm
parsing tài liệu, layout, bảng và cấu trúc. - **PP-StructureV3**: lựa
chọn đáng cân nhắc cho pipeline OCR/layout thiên về tài liệu. - OCR
riêng: dùng khi PDF scan hoặc text layer không đáng tin cậy.

Đầu ra parser nên được chuẩn hóa thành các element, ví dụ:

``` json
{
  "document_id": "doc_123",
  "page_number": 4,
  "element_id": "el_004_012",
  "element_type": "table",
  "text": null,
  "bbox": [72, 160, 520, 430],
  "reading_order": 12,
  "section_path": ["3. Kết quả", "3.2 KPI"],
  "caption": "Bảng 2. Kết quả theo quý",
  "source_ref": "object://documents/doc_123/page-4"
}
```

`bbox` là tọa độ bounding box; quy ước tọa độ cần thống nhất trong toàn
hệ thống. Ví dụ trên là cấu trúc minh họa, không phải output cố định của
một thư viện.

### Bước 3 --- Tạo Normalized Document IR

Chuẩn hóa mọi nguồn về một mô hình trung gian (Intermediate
Representation --- IR).

Các loại element tối thiểu:

-   `heading`
-   `paragraph`
-   `list_item`
-   `procedure_step`
-   `table`
-   `image`
-   `chart`
-   `caption`
-   `footnote`
-   `header_footer`
-   `page_break`

Mỗi element nên giữ: - `document_id`, `version_id`, `element_id` -
`page_number`, `reading_order`, `bbox` - `element_type`, `raw_text`,
`normalized_text` - `section_path`, `parent_element_id` - `source_ref`,
`parser_name`, `parser_version` - `confidence` nếu parser/OCR cung cấp
điểm tin cậy

Không loại bỏ ngay dữ liệu gốc khi chuẩn hóa; giữ raw output để kiểm tra
lỗi parsing.

### Bước 4 --- Phân loại tài liệu và section

Có thể phân loại bằng metadata đầu vào, quy tắc, classifier hoặc LLM.
Nên kết hợp tín hiệu thay vì phụ thuộc hoàn toàn vào LLM.

Ưu tiên: 1. Metadata được người dùng khai báo. 2. Quy tắc theo mẫu/tiêu
đề/cấu trúc. 3. Classifier hoặc LLM cho trường hợp chưa rõ. 4. Cho phép
loại `unknown` và dùng chiến lược fallback.

Tài liệu có thể là tài liệu hỗn hợp. Vì vậy, phân loại ở cấp section khi
cần, thay vì bắt buộc toàn bộ tài liệu chỉ có một loại.

## 4. Adaptive chunking theo loại tài liệu

  ----------------------------------------------------------------------------
  Loại tài liệu     Chiến lược chính   Quy tắc quan      Metadata gợi ý
                                       trọng             
  ----------------- ------------------ ----------------- ---------------------
  SOP / User Guide  Procedure-aware,   Giữ thứ tự bước;  `procedure_id`,
                    structure-aware    gắn cảnh báo và   `step_number`,
                                       ảnh minh họa với  `warning_level`,
                                       bước tương ứng    `section_path`

  Legal / ToS /     Hierarchy-aware    Tôn trọng điều,   `document_version`,
  Contract / Policy                    khoản, điểm; giữ  `article_id`,
                                       điều kiện, ngoại  `clause_id`,
                                       lệ và tham chiếu  `effective_date`
                                       chéo              

  Progress / Sprint Period-aware       Tách theo dự      `project_id`,
  / KPI Report                         án/kỳ báo cáo;    `report_period`,
                                       giữ tên chỉ số,   `metric_name`,
                                       đơn vị, chủ sở    `owner`, `status`
                                       hữu và trạng thái 

  Business Plan     Context-aware      Giữ giả định,     `plan_id`,
                                       kịch bản, đơn vị, `scenario`,
                                       tiền tệ, kỳ tài   `currency`, `unit`,
                                       chính, tiêu đề    `fiscal_period`
                                       bảng và chú thích 

  Internal Wiki /   Structure +        Tôn trọng         `department`,
  Handbook /        semantic           heading, danh     `topic`,
  Announcement                         sách và đoạn văn; `document_type`,
                                       semantic split    `updated_at`,
                                       trong phạm vi     `access_level`
                                       section           
  ----------------------------------------------------------------------------

### 4.1 SOP / User Guide

-   Xác định tiêu đề quy trình và từng bước.
-   Không tách nội dung điều kiện hoặc cảnh báo khỏi bước mà nó áp dụng.
-   Liên kết screenshot/diagram với bước tương ứng bằng
    `related_element_ids`.
-   Giữ `step_number` và thứ tự thực hiện.
-   Có thể dùng chunk cha là toàn bộ quy trình hoặc một nhóm bước; chunk
    con là từng bước/nhóm bước.

### 4.2 Legal / Contract / Policy

-   Dùng cấu trúc điều → khoản → điểm làm ranh giới ưu tiên.
-   Không cắt rời câu điều kiện, ngoại lệ, định nghĩa hoặc phần dẫn
    chiếu.
-   Lưu tham chiếu chéo, ví dụ `references: ["article_8_clause_2"]`.
-   Nếu một điều khoản dài, chia nhỏ theo đoạn nhưng giữ cùng
    `article_id` và `clause_id`.
-   Semantic similarity chỉ hỗ trợ trong ranh giới cấu trúc; không nên
    thay thế ranh giới pháp lý.

### 4.3 Progress / Sprint / KPI Report

-   Tách nội dung theo `project_id`, `report_period`, team hoặc chủ đề.
-   Bảng KPI phải giữ tên metric, đơn vị, kỳ báo cáo và hàng/cột liên
    quan.
-   Không trộn số liệu của nhiều kỳ vào cùng một chunk nếu có thể gây
    nhầm lẫn.
-   Lưu `owner`, `status`, `target`, `actual` và `period` khi có dữ
    liệu.

### 4.4 Business Plan

-   Giữ giả định, điều kiện áp dụng và kịch bản đi cùng dự báo.
-   Với bảng, giữ header, đơn vị, tiền tệ, kỳ tài chính và footnote.
-   Không áp dụng semantic chunking trực tiếp lên nội dung bảng đã
    chuyển thành text phẳng.
-   Tách các kịch bản khác nhau nếu số liệu hoặc giả định không giống
    nhau.

### 4.5 Internal Wiki / Handbook / Announcement

-   Tôn trọng heading, danh sách, bảng và các khối nội dung.
-   Semantic chunking áp dụng trong từng section sau khi đã xác định cấu
    trúc.
-   Giữ `updated_at`, `access_level` và phiên bản để tránh truy xuất nội
    dung cũ hoặc sai quyền.
-   Có thể tạo chunk con nhỏ cho retrieval và chunk cha lớn để mở rộng
    ngữ cảnh.

## 5. Xử lý riêng text, table, image và chart

### Text

-   Chuẩn hóa khoảng trắng và lỗi OCR nhưng giữ bản raw.
-   Ghép paragraph theo section và ngữ nghĩa.
-   Tránh trộn hai heading hoặc hai chủ đề không liên quan.
-   Bổ sung breadcrumb, ví dụ `Tài liệu > 3. Kết quả > 3.2 KPI`.

### Table

Mỗi bảng nên có representation có cấu trúc và một representation dạng
text phục vụ retrieval.

-   Giữ tiêu đề bảng, header, hàng, cột và thứ tự.
-   Lặp lại header khi chia bảng thành nhiều chunk.
-   Giữ đơn vị, tiền tệ, kỳ báo cáo, footnote và ghi chú.
-   Với bảng lớn, chia theo nhóm hàng nhưng mỗi chunk phải tự mô tả được
    các cột.
-   Có thể lưu JSON/HTML/Markdown chuẩn hóa bên cạnh text dùng để
    embedding.

Ví dụ nội dung embedding:

``` text
Bảng: Doanh thu theo quý
Đơn vị: tỷ VND
Kỳ: FY2025
Cột: Quý | Doanh thu | Tăng trưởng
Q1 | 12.4 | 4%
Q2 | 13.1 | 6%
```

### Image

-   Lưu ảnh gốc hoặc crop cùng `document_id`, `page_number`, `bbox`.
-   Trích xuất caption và OCR khi phù hợp.
-   Dùng vision model tạo mô tả chỉ khi cần và lưu riêng
    `generated_description`.
-   Liên kết ảnh với paragraph, bước SOP hoặc caption liên quan.
-   Không coi mô tả do AI sinh là văn bản gốc; cần đánh dấu nguồn và độ
    tin cậy.

### Chart

-   Ưu tiên trích xuất tiêu đề, trục, đơn vị, series, legend, thời gian
    và nhãn dữ liệu.
-   Nếu có thể, lưu dữ liệu chart thành bảng có cấu trúc.
-   Nếu chỉ có ảnh chart, dùng OCR/vision để tạo mô tả và đánh dấu đây
    là dữ liệu suy luận.
-   Liên kết chart với phần giải thích trong văn bản gần đó.

## 6. Mô hình dữ liệu chunk và quan hệ

Ví dụ schema logic:

``` json
{
  "chunk_id": "chk_001",
  "document_id": "doc_123",
  "version_id": "ver_2",
  "parent_id": "chk_parent_01",
  "element_ids": ["el_004_012"],
  "related_chunk_ids": ["chk_002"],
  "chunk_type": "table",
  "document_type": "progress_report",
  "content": "Bảng: Doanh thu theo quý...",
  "section_path": ["3. Kết quả", "3.2 KPI"],
  "page_start": 4,
  "page_end": 4,
  "metadata": {
    "project_id": "project_alpha",
    "report_period": "FY2025",
    "unit": "billion VND"
  },
  "source": {
    "uri": "object://documents/doc_123",
    "bbox": [72, 160, 520, 430]
  }
}
```

Các trường này là schema gợi ý. Có thể chuẩn hóa một số trường thành cột
SQL để lọc hiệu quả và lưu metadata linh hoạt trong JSONB.

### Quan hệ cần hỗ trợ

-   `parent_id`: chunk cha chứa ngữ cảnh rộng hơn.
-   `child_ids`: chunk con để truy xuất chi tiết.
-   `related_chunk_ids`: chunk liên quan, ví dụ bảng với phần giải
    thích.
-   `element_ids`: element nguồn tạo ra chunk.
-   `references`: điều khoản hoặc section được dẫn chiếu.
-   `previous_chunk_id` / `next_chunk_id`: dùng khi thứ tự nội dung quan
    trọng.

Không cần tạo mọi loại quan hệ ngay từ phiên bản đầu; triển khai các
quan hệ có giá trị cho retrieval và đánh giá trước.

## 7. Embedding và lưu trữ

Một kiến trúc triển khai thực tế có thể gồm:

-   **Object storage**: file gốc, ảnh, crop và artifacts của parser.
-   **PostgreSQL**: tài liệu, phiên bản, chunks, metadata, trạng thái
    job và quan hệ.
-   **pgvector hoặc vector database riêng**: vector embedding.
-   **Full-text search / BM25**: tìm kiếm từ khóa chính xác, mã, tên
    riêng và số điều khoản.
-   **Queue**: xử lý nền, retry và backpressure.

Với quy mô ban đầu, PostgreSQL + pgvector + full-text search có thể giảm
độ phức tạp vận hành. Chỉ tách vector database hoặc search engine riêng
khi benchmark cho thấy nhu cầu về quy mô, throughput, filtering hoặc vận
hành.

### Nguyên tắc embedding

-   Embed nội dung đã chuẩn hóa cùng đủ ngữ cảnh cần thiết, không chỉ
    một đoạn rời rạc.
-   Với bảng, đưa tên bảng, header, đơn vị và kỳ báo cáo vào text
    embedding.
-   Với ảnh, có thể embed caption/mô tả; nếu cần tìm kiếm ảnh trực tiếp,
    đánh giá thêm multimodal embedding.
-   Không embed metadata nhạy cảm hoặc nội dung mà người dùng không được
    phép truy cập.
-   Lưu `embedding_model`, `embedding_version` và thời điểm tạo vector
    để hỗ trợ re-index.

## 8. Retrieval pipeline

1.  **Query understanding**: nhận diện ý định, thực thể, kỳ thời gian,
    loại tài liệu và bộ lọc.
2.  **Permission filter**: áp dụng tenant/workspace và quyền truy cập
    trước khi trả kết quả.
3.  **Metadata filter**: lọc theo phiên bản, ngày hiệu lực, dự án, kỳ
    báo cáo hoặc loại tài liệu.
4.  **Hybrid retrieval**: chạy vector search và BM25; hợp nhất kết quả
    bằng phương pháp như Reciprocal Rank Fusion.
5.  **Reranking**: xếp hạng lại các ứng viên theo mức độ liên quan với
    câu hỏi.
6.  **Parent/relationship expansion**: bổ sung chunk cha, bảng, caption
    hoặc chunk liên quan khi cần.
7.  **Context assembly**: loại trùng, ưu tiên phiên bản đúng, giữ thứ tự
    và giới hạn token.
8.  **Answer generation**: yêu cầu LLM chỉ kết luận từ nguồn đã truy
    xuất; nếu thiếu bằng chứng, nói rõ.
9.  **Citation**: trả nguồn gồm tên tài liệu, phiên bản, trang và
    section/element phù hợp.

Không nên mở rộng tất cả chunk liên quan một cách vô hạn. Chỉ mở rộng
khi có ích, có giới hạn số lượng và token budget.

## 9. Gợi ý chunk size ban đầu

Các khoảng dưới đây là điểm khởi đầu để benchmark, tính theo token;
không phải quy tắc cố định.

  ------------------------------------------------------------------------
  Loại                             Khoảng thử nghiệm Ghi chú
  --------------------- ---------------------------- ---------------------
  SOP / User Guide                          300--600 Ưu tiên nhóm bước
                                                     hoàn chỉnh

  Legal                                     300--800 Không cắt điều khoản
                                                     tùy tiện; có thể vượt
                                                     khoảng nếu cần giữ
                                                     nguyên nghĩa

  Progress / KPI Report                     300--700 Tách theo kỳ/dự án;
                                                     bảng có quy tắc riêng

  Business Plan                            500--1000 Giữ giả định và ngữ
                                                     cảnh tài chính

  Internal Wiki                             300--600 Semantic split trong
                                                     section
  ------------------------------------------------------------------------

Thiết lập thêm: - `max_tokens`: giới hạn kỹ thuật theo
embedding/model. - `overlap`: chỉ dùng khi cần; tránh overlap lớn gây
trùng lặp. - `min_chunk_size`: hạn chế chunk quá ngắn, nhưng không gộp
các điều khoản độc lập. - `semantic_threshold`: thử nghiệm nhiều giá trị
trên tập đánh giá, không chọn ngưỡng cố định theo cảm tính.

Cần benchmark theo chất lượng retrieval và câu trả lời, không chỉ theo
độ dài chunk.

## 10. Pseudocode điều phối chunking

``` python
def process_document(document):
    parsed = parse_with_layout(document)
    ir = normalize_to_ir(parsed)

    document_type = classify_document(ir, document.metadata)
    sections = split_into_sections(ir)

    chunks = []

    for section in sections:
        section_type = classify_section(section, fallback=document_type)

        if section_type == "sop":
            section_chunks = chunk_procedure(section)
        elif section_type == "legal":
            section_chunks = chunk_legal_hierarchy(section)
        elif section_type == "progress_report":
            section_chunks = chunk_by_project_and_period(section)
        elif section_type == "business_plan":
            section_chunks = chunk_context_aware(section)
        else:
            section_chunks = chunk_structure_then_semantic(section)

        chunks.extend(section_chunks)

    element_chunks = []
    for element in ir.elements:
        if element.type == "table":
            element_chunks.extend(process_table(element))
        elif element.type == "image":
            element_chunks.extend(process_image(element))
        elif element.type == "chart":
            element_chunks.extend(process_chart(element))

    all_chunks = merge_without_losing_element_identity(chunks, element_chunks)
    all_chunks = enrich_context_and_relationships(all_chunks, ir)
    all_chunks = validate_and_deduplicate(all_chunks)

    persist_chunks(all_chunks)
    embed_and_index(all_chunks)

    return {
        "document_id": document.id,
        "chunk_count": len(all_chunks),
        "status": "indexed",
    }
```

Các hàm trong ví dụ là interface minh họa cần tự triển khai hoặc ánh xạ
vào thư viện đã chọn; đây không phải module Python có thể chạy nguyên
trạng.

## 11. Metadata tối thiểu đề xuất

### Metadata chung

-   `tenant_id` / `workspace_id`
-   `document_id`, `version_id`
-   `document_type`, `chunk_type`
-   `title`, `section_path`
-   `page_start`, `page_end`
-   `source_uri`, `element_ids`
-   `created_at`, `updated_at`
-   `access_level` / ACL
-   `parser_name`, `parser_version`
-   `embedding_model`, `embedding_version`

### Metadata chuyên biệt

-   SOP: `procedure_id`, `step_number`, `warning_level`
-   Legal: `article_id`, `clause_id`, `effective_date`, `references`
-   Report: `project_id`, `report_period`, `metric_name`, `owner`,
    `status`
-   Business plan: `plan_id`, `scenario`, `currency`, `unit`,
    `fiscal_period`
-   Wiki: `department`, `topic`, `updated_at`, `access_level`

Metadata phải được dùng trong truy vấn và kiểm soát quyền, không chỉ lưu
cho có. Với multi-tenant, lọc quyền truy cập phải được thực thi ở
backend trước khi context được đưa vào LLM.

## 12. Đánh giá chất lượng

Xây dựng tập câu hỏi kiểm thử đại diện cho từng loại tài liệu. Mỗi câu
hỏi nên có câu trả lời mong đợi, nguồn đúng và mức độ khó.

Đo các chỉ số:

-   **Parsing**: độ chính xác thứ tự đọc, nhận diện heading, bảng, OCR
    và caption.
-   **Retrieval**: Recall@k, Precision@k, MRR hoặc nDCG.
-   **Answer**: groundedness, correctness, citation precision và tỷ lệ
    trả lời khi không đủ bằng chứng.
-   **Operations**: thời gian ingest, thời gian truy vấn, chi phí
    embedding/LLM, tỷ lệ job lỗi và thời gian re-index.

Thử nghiệm ablation: 1. Fixed/recursive chunking làm baseline. 2.
Structure-aware chunking. 3. Structure-aware + document-specific
strategy. 4. Hybrid retrieval. 5. Hybrid + reranker. 6.
Parent/related-element expansion.

Chỉ giữ các thành phần phức tạp nếu chúng cải thiện kết quả trên bộ đánh
giá.

## 13. Lộ trình triển khai

### Phase 1 --- MVP

-   PDF/DOCX ingestion.
-   Parse layout và tạo IR.
-   Structure-aware text chunking.
-   PostgreSQL + pgvector + full-text search.
-   Metadata filter, retrieval và citation trang.
-   Logging, retry và bộ câu hỏi đánh giá nhỏ.

### Phase 2 --- Document-specific chunking

-   Phân loại 5 nhóm tài liệu.
-   SOP/procedure chunker và legal hierarchy chunker.
-   Report period-aware chunker.
-   Bổ sung parent-child và section breadcrumb.

### Phase 3 --- Multimodal

-   Table normalization và row-group chunking.
-   Image crop, caption, OCR/vision.
-   Chart extraction.
-   Liên kết text-table-image-chart.

### Phase 4 --- Chất lượng và mở rộng

-   Reranker và hybrid rank fusion.
-   Versioning, ACL và multi-tenant hardening.
-   Re-index theo parser/embedding version.
-   Evaluation pipeline, monitoring và cost controls.

## 14. Quyết định kiến trúc khuyến nghị

1.  **Dùng parser/layout analyzer trước khi chunking**, đặc biệt với PDF
    nhiều cột và tài liệu có bảng/hình.
2.  **Dùng IR làm ranh giới giữa parsing và chunking** để có thể thay
    parser mà không viết lại toàn bộ pipeline.
3.  **Dùng strategy router theo document/section type** thay vì một
    chunker duy nhất.
4.  **Lưu chunk text và cấu trúc gốc song song**, nhất là bảng và chart.
5.  **Dùng chunk nhỏ cho retrieval, chunk cha cho ngữ cảnh** khi cần;
    đây là chiến lược retrieval bổ sung, không thay thế chunking theo
    cấu trúc.
6.  **Bắt đầu đơn giản với PostgreSQL + pgvector + full-text search**,
    sau đó benchmark trước khi thêm hệ thống khác.
7.  **Đánh giá bằng tập câu hỏi thực tế** để chọn chunk size, overlap,
    embedding và reranker.

## 15. Checklist trước production

-   [ ] Có `document_id` và `version_id` ổn định.
-   [ ] Có lưu file gốc và parser artifacts.
-   [ ] Đã kiểm tra PDF nhiều cột, scan, bảng nhiều trang và hình có
    caption.
-   [ ] Có fallback cho parser/OCR thất bại.
-   [ ] Có metadata và ACL ở cấp document/chunk.
-   [ ] Có hybrid retrieval và citation về trang/section.
-   [ ] Có kiểm thử tránh trộn phiên bản hoặc kỳ báo cáo.
-   [ ] Có bộ câu hỏi đánh giá và baseline.
-   [ ] Có logging, retry, idempotency và khả năng re-index.
-   [ ] Có giới hạn chi phí, token và mở rộng context.
