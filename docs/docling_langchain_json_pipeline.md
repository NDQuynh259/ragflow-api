# Docling → LangChain và JSON trung gian

Pipeline bật OCR để đọc chữ nằm trong bitmap của file scan. OCR chỉ tạo nội dung text; Docling vẫn tách bảng và hình ảnh thành các record riêng.

Chạy:

```powershell
python scripts/docling_langchain_pipeline.py input.pdf outputs/docling
```

Pipeline tạo ba file:

1. `01_docling.json`: schema gốc của Docling, gồm text, table, picture và layout.
2. `02_text.json`, `02_tables.json`, `02_images.json`: ba nhánh dữ liệu tách riêng, có page/bbox và Docling reference.
3. `03_langchain_documents.json`: text, table và image placeholder được chuyển thành các LangChain Document riêng, có `kind` và `source_id`.
4. `04_langchain_chunks.json`: chunk sau khi cắt; metadata được giữ để nối citation về file nguồn.

Ảnh bitmap được giữ riêng trong `02_images.json`; phần chữ OCR được đưa vào `02_text.json` theo block và page/bbox. Bảng được đưa vào `02_tables.json` theo cell. Vì vậy mỗi loại có thể xử lý và embedding riêng trước khi đưa vào LangChain.
