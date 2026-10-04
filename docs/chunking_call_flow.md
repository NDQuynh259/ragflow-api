# Luồng Gọi Hàm Chunking

Sơ đồ này mô tả luồng gọi hàm thực tế của pipeline chunking trong `rag-document-pipeline`.

## Cấu trúc Package

```text
chunking/
├── __init__.py          # Public exports và compatibility aliases
├── base.py              # Protocol, estimate_tokens, group_by_section
├── section.py           # propagate_sections, group_by_section
├── multimodal.py        # MultimodalChunker router (MultimodalChunker alias)
├── text.py              # TextChunker (TextChunker alias)
├── table.py             # TableChunker
└── image.py             # ImageChunker
```

## 1. Luồng tổng thể

```mermaid
flowchart TD
    A[DocumentPipeline.process] --> B[parser.parse]
    B --> C[DocumentPipeline._normalize]
    C --> D[LayoutNormalizer.bind_captions_and_footnotes]
    D --> E[MultimodalChunker.chunk]
    E --> F[Multimodal reading-order router]

    F -->|Text / List / Formula| G[Accumulate adjacent text]
    G --> H[TextChunker.chunk]

    F -->|Bảng nhỏ| I[TableChunker.render_markdown]
    I --> G
    F -->|Bảng lớn| J[TableChunker.chunk]
    F -->|Image/Figure| K[ImageChunker.chunk]

    H --> L[Merge theo reading order]
    J --> L
    K --> L

    L --> M[Re-index sequentially]

    M --> N[DocumentPipeline._validate]
    N --> O[ProcessedDocument]
```

## 2. Luồng xử lý heading và nhóm section

```mermaid
sequenceDiagram
    participant C as MultimodalChunker.chunk
    participant P as _propagate_sections
    participant G as _group_by_section
    participant L as LayoutElement[]

    C->>P: _propagate_sections(elements)
    loop từng element theo reading order
        P->>P: Nếu heading: cập nhật heading_stack
        P->>L: Gán section_path cho element kế tiếp
    end
    P-->>C: elements có section_path
    C->>G: _group_by_section(elements)
    G->>G: Gom phần tử liền kề cùng section_path và page_number
    G-->>C: list[list[LayoutElement]]
```

### Quy tắc `heading_stack`

```text
H1: Chương 1
    section_path = [Chương 1]

H2: 1.1 Phạm vi
    section_path = [Chương 1, 1.1 Phạm vi]

paragraph
    section_path = [Chương 1, 1.1 Phạm vi]

H1: Chương 2
    section_path = [Chương 2]
```

## 3. Luồng semantic text chunking

```mermaid
flowchart TD
    A[TextChunker.chunk] --> B[_group_by_section]
    B --> C[Cho từng group]
    C --> D[_heading_prefix]
    C --> E[_group_text từng element]
    E -->|table có table_data| F[TableChunker.render_markdown]
    E -->|text/khác| G[el.text.strip]
    F --> H[Nối bằng blank line]
    G --> H
    H --> I[_split_semantically]

    I --> J[_split_sentences]
    J --> K[_collect_blocks tách bảng Markdown khỏi văn bản]
    K --> L{Block là bảng?}
    L -->|Có| M[Giữ nguyên atomic table block]
    L -->|Không| N[Mask decimal và viết tắt bằng U+E000]
    N --> O[Split theo . ? ! ; … và newline]
    O --> P[Unmask dấu chấm]
    M --> Q[list sentences]
    P --> Q

    Q --> R[_compute_distances window_size=2]
    R --> S{embed_fn?}
    S -->|Có| T[Batch embedding toàn bộ buffers]
    T --> U[Cosine distance]
    S -->|Không hoặc lỗi| V[Jaccard lexical distance]
    U --> W[list distances]
    V --> W

    W --> X[_calculate_threshold theo percentile]
    X --> Y[Tách khi distance >= threshold]
    Y --> Z[_enforce_bounds]
    Z --> AA{segment < min_chunk_size?}
    AA -->|Có và có segment trước| AB[_merge_segments nối vào chunk trước]
    AA -->|Không| AC[Giữ segment]
    AB --> AD
    AC --> AD{segment > max_chunk_size?}
    AD -->|Có| AE[_recursive_split theo \n\n, \n, . , ,]
    AD -->|Không| AF[Giữ segment]
    AE --> AG[list segments]
    AF --> AG

    AG --> AH[Gắn heading prefix]
    AH --> AI[DocumentChunk với modality=text]
    AI --> AJ[estimate_tokens]
```

## 4. Chi tiết semantic distance

```mermaid
sequenceDiagram
    participant S as _split_semantically
    participant D as _compute_distances
    participant E as embed_fn
    participant J as Jaccard fallback

    S->>D: sentences, window_size=2
    D->>D: Tạo left_buffer và right_buffer cho từng boundary
    alt embed_fn được truyền vào
        D->>E: embed_fn(left_buffers + right_buffers)
        E-->>D: vectors
        D->>D: Tính 1 - cosine_similarity
    else embed_fn=None hoặc bị lỗi
        D->>J: tokenize bằng regex \\w+
        J-->>D: 1 - intersection/union
    end
    D-->>S: distances
    S->>S: threshold = percentile(distances, 80)
    S->>S: split khi distance >= threshold
```

## 5. Luồng bảng và hình ảnh

```mermaid
flowchart LR
    A[LayoutElement] --> B{type}
    B -->|text/list/formula| C[Accumulate adjacent text]
    C --> D[TextChunker]

    B -->|bảng nhỏ| E[TableChunker.render_markdown]
    E --> C

    B -->|bảng lớn| F[TableChunker.chunk]
    F --> G[_chunk_table]
    G --> H{full markdown <= chunk_size?}
    H -->|Có| I[1 table DocumentChunk]
    H -->|Không| J[Chia theo row groups]
    J --> K[Lặp header mỗi chunk]

    B -->|image/figure| L[ImageChunker.chunk]
    L --> M[_chunk_image]
    M --> N[Gom caption/description/OCR/element text/footnote]
    N --> O{Có text?}
    O -->|Có| P[indexable=True]
    O -->|Không| Q[indexable=False, token_count=0]
```

## 6. Thứ tự hàm chính

### Pipeline đầy đủ

```text
DocumentPipeline.process
├── parser.parse
├── DocumentPipeline._normalize
│   ├── _clean_text (từng element)
│   └── LayoutNormalizer.bind_captions_and_footnotes
├── MultimodalChunker.chunk
│   ├── _propagate_sections
│   └── Multimodal reading-order router
│       ├── _group_by_section
│       ├── TableChunker.is_small_table
│       ├── TableChunker.render_markdown (bảng nhỏ)
│       ├── TextChunker.chunk
│       │   ├── _heading_prefix
│       │   ├── _group_text
│       │   └── _split_semantically
│       │       ├── _split_sentences
│       │       ├── _compute_distances
│       │       ├── _calculate_threshold
│       │       ├── _join_sentences
│       │       └── _enforce_bounds
│       ├── TableChunker.chunk (bảng lớn)
│       │   └── _chunk_table
│       └── ImageChunker.chunk
│           └── _chunk_image
├── DocumentPipeline._validate
└── ProcessedDocument
```

## 7. Routing duy nhất

Hệ thống luôn dùng một router multimodal theo reading order:

| Modality | Cách xử lý |
|---|---|
| Text/list/formula | Gom các element liền kề và semantic chunking |
| Bảng nhỏ | Render Markdown và inline vào text batch liền kề |
| Bảng lớn | Chunk độc lập theo nhóm hàng, lặp header |
| Image/figure | Chunk độc lập từ caption/OCR/description/footnote |
| Header/footer | Bỏ qua |

Không còn tham số `multimodal_routing`: router multimodal là luồng duy nhất. Cấu hình chỉ gồm `chunk_size`, `min_chunk_size`, `max_chunk_size`, `threshold_percentile` và `embed_fn`.

## 8. Các hàm tiện ích

- `group_by_section()` — gom phần tử liền kề cùng `section_path` và `page_number`.
- `estimate_tokens()` — ước lượng token bằng `len(text) // 4`.
- `TableChunker.render_markdown()` — render bảng thành Markdown để inline hoặc xuất trực tiếp.
- `TableChunker.is_small_table()` — quyết định bảng có được inline hay không.
