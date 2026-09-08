# Luồng retrieval và generation

```text
Query → permission filter → query rewrite → hybrid retrieval
      → rerank → context compression → prompt → LLM
      → citation validation → response
```

## Quy tắc truy hồi

1. Business API lấy danh sách document user được phép dùng.
2. RAG Core tiếp tục filter bằng `tenant_id` và `document_ids`.
3. Lấy candidate bằng dense vector và sparse/BM25.
4. Reranker chọn các chunk liên quan nhất.
5. Context builder loại duplicate, giữ heading/table và giới hạn token.
6. LLM chỉ được dùng context đã cung cấp.

## Kết quả

Response phải gồm:

```json
{
  "answer": "...",
  "citations": [
    {
      "document_id": "...",
      "chunk_id": "...",
      "page_number": 3,
      "bbox": [72, 350, 500, 391],
      "quote": "..."
    }
  ],
  "usage": {"prompt_tokens": 0, "completion_tokens": 0}
}
```

Nếu không có nguồn đạt ngưỡng, trả lời rõ ràng rằng tài liệu không đủ thông tin. Không tạo citation giả.
