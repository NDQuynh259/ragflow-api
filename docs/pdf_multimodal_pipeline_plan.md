# Kế hoạch cải thiện pipeline PDF, hình ảnh và diagram

## 1. Mục tiêu

Xử lý ổn định tài liệu `sop_la_gi_vnce_co_hinh_anh.pdf` và các PDF tương tự có:

- text layer;
- paragraph, heading và list;
- bảng thường/nested;
- vector diagram/flowchart;
- bitmap image và icon;
- diagram composite gồm nhiều thành phần;
- tiếng Việt và Unicode;
- nội dung cần đưa vào text-based RAG.

Pipeline mục tiêu:

```text
PDF
→ parse layout/text/table/image/vector
→ normalize encoding
→ phát hiện figure region
→ gom thành phần figure/diagram
→ OCR/vision enrichment có chọn lọc
→ tạo structured text
→ chunk theo loại nội dung
→ embedding/indexing
```

Không đặt mục tiêu biến một parser thành hệ thống hiểu hoàn hảo mọi loại tài liệu. Parser chịu trách nhiệm trích xuất cấu trúc; OCR/vision chỉ bổ sung cho vùng khó.

## 2. Tài liệu mẫu chỉ dùng làm regression fixture

Các chi tiết như `Hình 1`, `Hình 2`, `Hình 3`, trang 1/2/4 và các nhãn `Management/Employees` **không được hard-code vào pipeline**. Chúng chỉ là fixture để kiểm thử hồi quy.

Với một PDF bất kỳ, pipeline phải phát hiện động dựa trên layout, caption, loại element, bbox và tín hiệu nội dung. Không được giả định trước số trang, số hình, số cột, tên section hay loại diagram.

## 3. Đặc điểm file mẫu

File mẫu có 5 trang và cần được phân loại như sau:

| Trang | Nội dung | Xử lý mục tiêu |
|---|---|---|
| 1 | Infographic SOP với 4 giá trị cốt lõi, gồm text/vector và icon/bitmap | Composite central-concept diagram |
| 2 | Flowchart 8 bước, nhiều box và connector | Flowchart diagram |
| 3 | Text/list | Heading-aware text chunks |
| 4 | Diagram hai nhánh quản lý/nhân viên và bảng | Composite diagram + table-aware chunks |
| 5 | Bảng và text | Table-aware + text chunks |

Các lỗi hiện tại cần giải quyết:

- list/table nested bị chuyển thành text rỗng hoặc metadata nội bộ;
- mỗi image bị coi là một figure độc lập;
- vector diagram ở trang 1/2 không được gom thành figure;
- caption có thể bị gán trùng cho nhiều group;
- text tiếng Việt trong output có dấu hiệu mojibake;
- image được extract nhưng chưa có OCR/description/representation để embedding;
- relation/node/edge của flowchart chưa được biểu diễn rõ.

## 4. Phase 1 — Chuẩn hóa model dữ liệu

### File

`packages/rag-document-pipeline/src/rag_document_pipeline/models.py`

### Việc cần làm

1. Chuẩn hóa các loại element:

   ```text
   text, heading, paragraph, list, table,
   image, figure, caption, shape, connector, diagram_label
   ```

2. Bổ sung model trung gian `FigureRegion`:

   ```python
   class FigureRegion(BaseModel):
       id: str
       page_number: int
       bbox: tuple[float, float, float, float] | None = None
       caption: str | None = None
       title: str | None = None
       element_ids: list[str] = Field(default_factory=list)
       text_elements: list[str] = Field(default_factory=list)
       image_sources: list[str] = Field(default_factory=list)
       ocr_text: list[str] = Field(default_factory=list)
       description: str | None = None
       diagram_type: str | None = None
       nodes: list[dict[str, Any]] = Field(default_factory=list)
       edges: list[dict[str, Any]] = Field(default_factory=list)
       confidence: float | None = None
       metadata: dict[str, Any] = Field(default_factory=dict)
   ```

3. Chuẩn hóa `DocumentChunk.kind` tối thiểu thành:

   ```text
   text, table, figure, diagram
   ```

4. Metadata chunk phải giữ được `page`, `figure_id`, `diagram_type`, `element_ids`, `confidence`, `image_sources` và trạng thái phát hiện relation.

## 5. Phase 2 — Sửa OpenDataLoader parser

### File

`packages/rag-document-pipeline/src/rag_document_pipeline/parsers/opendataloader.py`

### 4.1. Parse recursive

Xử lý đệ quy các field:

```text
kids, children, items, list_items, rows, cells, content
```

Các cấu trúc cần hỗ trợ:

```text
list → kids/items → paragraph → content
table → rows → cells → kids → paragraph → content
```

Kết quả không được còn dạng:

```json
{"type": "list", "text": ""}
```

nếu node con thực sự có nội dung.

### 4.2. Flatten nested elements

Flatten node con thành `LayoutElement` khi node có `id`, `type`, `page`, `bbox` hoặc text. Tránh duplicate khi parent và child đã được xuất ở cùng level.

### 4.3. Chuẩn hóa bbox

Hỗ trợ bbox dạng list, dict và chuỗi; luôn chuẩn hóa về:

```text
x0 <= x1
y0 <= y1
```

### 4.4. Nhận diện caption

Nhận diện các prefix:

```text
Hình, Hinh, Figure, Fig., Sơ đồ, So do, Diagram
```

Caption là anchor cho việc phát hiện figure region.

### 4.5. Kiểm tra encoding

Xác định mojibake xuất hiện ở nguồn nào: OpenDataLoader, JSON, adapter hay console. Đọc/ghi file UTF-8 rõ ràng; chỉ repair khi có pattern mojibake chắc chắn và có thể kiểm chứng.

## 6. Phase 3 — Figure region detector và grouping tổng quát

### Module đề xuất

```text
packages/rag-document-pipeline/src/rag_document_pipeline/figures/
├── __init__.py
├── detector.py
├── grouping.py
├── classifier.py
└── formatter.py
```

### Nguyên tắc

Không dùng quy tắc:

```text
mỗi image = một figure
```

Mà dùng:

```text
caption/diagram region = một figure
```

### Thuật toán

1. Tìm caption theo page.
2. Thu thập các element trực quan nằm phía trên caption.
3. Dùng page, bbox, dải y, vùng visual và section boundary để loại element không liên quan.
4. Cho phép nhiều cột/nhánh cùng thuộc một figure nếu có caption chung.
5. Merge các group chồng lấn, có element chung hoặc cùng caption.
6. Tính bbox bao toàn figure.
7. Loại element đã thuộc figure khỏi text chunking thông thường.

Đối với PDF bất kỳ, detector phải tạo được danh sách figure region động. Với file mẫu, kết quả kỳ vọng là:

```text
Hình 1 → một central-concept figure
Hình 2 → một flowchart figure
Hình 3 → một composite two-column figure
```

## 7. Phase 4 — Phân loại và format diagram

### Phân loại tổng quát

Không phân loại dựa trên số hình hoặc tên hình. Dùng tín hiệu kết hợp:

- caption và từ khóa trong caption;
- mật độ text/shape/image;
- connector/arrow và hướng đọc;
- số node, số cột, số hàng;
- pattern `step`, `phase`, `input`, `output`, `process`;
- bố cục trung tâm-xung quanh, tuyến tính, cây, lưới hoặc hai cột;
- tỷ lệ vùng ảnh và vùng text;
- kết quả của layout parser/vision model nếu có.

Các class chỉ là heuristic, có thể mở rộng:

```text
flowchart, process, timeline, central_concept,
hierarchy, comparison, architecture, network,
chart, table_figure, infographic, unknown_visual
```

Nếu confidence thấp, dùng representation trung tính thay vì tự suy đoán loại diagram.

### Hình 1 — Central concept

Structured text cần có:

```text
[DIAGRAM]
Figure: Hình 1
Title: SOP với 4 giá trị cốt lõi

[CORE]
SOP - Standard Operating Procedure

[COMPONENTS]
- Đảm bảo chất lượng: ...
- Giảm thiểu sai sót: ...
- Tối ưu hiệu suất: ...
- Đào tạo chuẩn hóa: ...

[LAYOUT]
Bốn thành phần được bố trí xung quanh SOP trung tâm.
```

### Hình 2 — Flowchart

Structured text cần có:

```text
[DIAGRAM]
Figure: Hình 2
Type: Flowchart

[FLOW]
Bước 1 → Bước 2 → Bước 3 → Bước 4
Bước 5 → Bước 6 → Bước 7 → Bước 8

[STEPS]
1. Mục tiêu SOP: ...
...
8. Cập nhật định kỳ: ...
```

Chỉ ghi edge khi connector/reading order xác định được. Nếu không, ghi rõ relation chưa chắc chắn.

### Hình 3 — Composite two-column

Gom title chung, nhánh Management, nhánh Employees, icon/image, list và caption vào một figure region. Không tạo hai figure chunk riêng cho hai image bitmap.

## 8. Phase 5 — Bitmap/OCR/vision enrichment

### Nguyên tắc selective enrichment

Không OCR toàn bộ PDF nếu text layer đã tốt. Dùng:

```text
text layer → native extraction
bitmap/scan/vùng thiếu text → OCR
diagram/chart khó → vision description
```

### Bitmap

Lưu image source, page, bbox; OCR khi ảnh có text hoặc nằm trong vùng diagram; giữ confidence.

### Vision

Chỉ dùng cho vùng cần hiểu hình. Output nên là structured JSON gồm:

```json
{
  "title": "...",
  "components": [],
  "nodes": [],
  "edges": [],
  "layout": "...",
  "description": "...",
  "uncertainties": []
}
```

Không bỏ ảnh gốc sau khi tạo text.

## 9. Phase 6 — Chunking theo loại nội dung

### Modules

Triển khai các file đang là TODO:

```text
chunkers/base.py
chunkers/heading_aware.py
chunkers/semantic.py
```

Bổ sung logic:

- text: chunk theo heading/paragraph, ưu tiên không cắt giữa câu;
- table: giữ title/header/row/page/row-column metadata;
- diagram: một overview chunk cho figure nhỏ;
- diagram lớn: overview + component chunks + relation/flow chunk nếu có.

Mọi chunk con phải giữ `figure_id` để truy vết về figure gốc.

## 10. Phase 7 — Refactor `DocumentPipeline`

### File

`packages/rag-document-pipeline/src/rag_document_pipeline/pipeline.py`

### Flow mới

```python
elements = parser.parse(...)
elements = normalize_elements(elements)

figure_regions = detect_figure_regions(elements)
figure_regions = enrich_figure_regions(figure_regions)
diagram_chunks = build_diagram_chunks(figure_regions)

normal_elements = remove_figure_elements(elements, figure_regions)
text_chunks = chunk_text_elements(normal_elements)
table_chunks = chunk_tables(normal_elements)

chunks = merge_and_sort_chunks(
    text_chunks,
    table_chunks,
    diagram_chunks,
)
```

Không để element trong figure tiếp tục bị chunk lại thành text rời; không duplicate caption.

## 11. Phase 8 — Tích hợp RAG

Index `content` cùng metadata:

```text
document_id
page_start/page_end
kind
figure_id
diagram_type
element_ids
confidence
image_sources
```

Có thể ưu tiên retrieval theo `kind`:

- câu hỏi về flowchart → `diagram`;
- câu hỏi về bảng → `table`;
- câu hỏi tổng quát → text + table + diagram;
- không trộn chat memory vào document context nếu không cần.

## 12. Test và acceptance criteria

### Parser tests tổng quát

- Không phụ thuộc số trang hoặc thứ tự hình.
- PDF không có caption vẫn có thể tạo visual region bằng layout clustering.
- PDF có nhiều cột vẫn giữ được page/bbox và reading order.
- PDF chỉ có text không sinh figure chunk giả.
- PDF chỉ có ảnh vẫn sinh image/figure region có confidence phù hợp.
- Nhiều hình gần nhau nhưng có caption riêng không bị merge nhầm.
- Một diagram gồm nhiều cột/bitmap/vector được merge nếu có bằng chứng cùng region.

### Regression tests cho file mẫu

- Trang 1 có đủ 4 component của Hình 1.
- Trang 2 có đủ 8 bước của Hình 2.
- Trang 4 tạo được một group Hình 3, không phải hai group image độc lập.
- Nested list/table có text thật.
- Bbox được normalize.

### Chunk tests

- Có một diagram chunk cho mỗi Hình 1, Hình 2, Hình 3.
- Caption mỗi hình chỉ xuất hiện một lần.
- Image element đã thuộc composite figure không tạo chunk rời.
- Bảng không còn text kiểu `type | row number | id | cells` thay cho nội dung thật.

### Encoding tests

- Text tiếng Việt hiển thị đúng: `Đảm bảo`, `Quản lý`, `Nhân viên`, `Quy trình`.
- Không xuất hiện pattern mojibake rõ ràng như `Ã`, `Â`, `áº`, `á»` trong output đã normalize.

### RAG evaluation questions

1. SOP có những giá trị cốt lõi nào?
2. Hình 1 mô tả những yếu tố nào?
3. Quy trình 8 bước bắt đầu và kết thúc ở đâu?
4. Bước 5 có mục đích gì?
5. Hình 3 gồm những nhóm vai trò nào?
6. Bảng trang 4 so sánh những lĩnh vực nào?
7. Quan hệ giữa người quản lý và nhân viên được mô tả thế nào?

Answer phải có page/figure metadata, phân biệt thông tin trực tiếp với suy luận, và nói rõ khi relation không được xác định chắc chắn.

## 13. Thứ tự triển khai

### P0 — Không để mất dữ liệu

1. Recursive parse `kids/items/rows/cells`.
2. Sửa list/table text rỗng.
3. Normalize bbox.
4. Kiểm tra/sửa UTF-8.
5. Thêm parser regression tests.

### P1 — Xử lý ba diagram trong file mẫu

1. Caption detection.
2. Figure region grouping.
3. Composite merge.
4. Structured formatter cho Hình 1/2/3.
5. Diagram chunks và tests.

### P2 — Enrichment

1. Lưu bitmap source.
2. OCR chọn lọc.
3. Vision description cho vùng khó.
4. Node/edge extraction.
5. Confidence/uncertainty.

### P3 — Chunk/RAG

1. Table-aware chunking.
2. Heading-aware chunking.
3. Diagram-aware chunking.
4. Citation metadata.
5. Retrieval filter theo `kind`/`figure_id`.

### P4 — Production

1. Cấu hình OpenDataLoader Hybrid/Docling.
2. Retry/timeout/cache cho enrichment.
3. Logging và metrics.
4. Regression corpus cho nhiều loại PDF.

## 14. Kiến trúc mục tiêu

```text
OpenDataLoader / Docling
        ↓
Recursive Layout Normalizer
        ↓
Figure Region Detector
        ↓
Bitmap/OCR/Vision Enricher
        ↓
Structured Document Model
        ↓
Text/Table/Diagram Chunkers
        ↓
Vector Index
        ↓
Grounded RAG Answer
```

Tiêu chí quan trọng nhất: sửa lỗi mất cấu trúc trước khi tối ưu `chunk_size`. Với file mẫu, chất lượng phụ thuộc trước hết vào recursive parsing và figure grouping, không phải chỉ vào cách chia chuỗi text.
