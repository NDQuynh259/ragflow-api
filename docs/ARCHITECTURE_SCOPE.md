# Phạm vi kiến trúc hiện tại

Backend hiện được giữ ở dạng modular monolith và chỉ triển khai pipeline PDF:

```text
PDF -> LayoutParser -> Text/Table/Image -> document_nodes
                                  -> PostgreSQL + pgvector
Query -> vector hoặc PostgreSQL FTS -> RRF (k=60)
      -> neighbor expansion/context merge -> RAG prompt -> LLM -> citations
```

## Module được giữ

- `app/ingestion/parsers/layout_parser.py`: tách text, table và image block.
- `app/ingestion/chunkers/semantic.py`: semantic chunking hiện tại dựa trên paragraph/recursive splitter.
- `app/ingestion/pipeline.py`: tạo node và embedding trong một transaction.
- `app/storage/database/` và `app/storage/vector/pgvector.py`: PostgreSQL, FTS, pgvector và RRF.
- `app/retrieval/pipeline.py`: retrieval, neighbor expansion và context merge.
- `app/generation/`: prompt citation và multimodal-ready LLM adapter.

## Module đã loại bỏ

Các loader ngoài PDF, extractor rỗng, Qdrant/MinIO adapter chưa triển khai, MCP/agent/worker stub,
chunker strategy trùng lặp, retriever/expansion/reranker wrapper không được gọi, domain graph cũ,
prompt không dùng và provider Cohere đã bị xóa để tránh tạo nhiều đường triển khai không có trong
pipeline thực tế.

## Giới hạn có chủ ý

Image node hiện được lưu metadata để dành cho bước classify/vision; chưa gọi vision model hoặc lưu
artifact MinIO. Retrieval hiện dùng PostgreSQL FTS (`ts_rank_cd`) thay cho BM25 engine chuyên dụng;
cross-encoder reranker và parent-child expansion chưa phải một phần của runtime hiện tại.
