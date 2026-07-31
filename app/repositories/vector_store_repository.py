"""PostgreSQL/pgvector persistence and retrieval queries."""

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.models import DocumentChunk


class VectorStoreRepository:
    @staticmethod
    def add_chunks(db: Session, chunks_data: list[dict[str, Any]]) -> int:
        inserted_count = 0
        for chunk in chunks_data:
            db.add(
                DocumentChunk(
                    document_id=chunk["document_id"],
                    chunk_index=chunk["chunk_index"],
                    content=chunk["content"],
                    metadata_json=chunk.get("metadata", {}),
                    embedding=chunk["embedding"],
                )
            )
            inserted_count += 1
            if inserted_count % settings.DB_INSERT_BATCH_SIZE == 0:
                db.flush()

        if inserted_count % settings.DB_INSERT_BATCH_SIZE:
            db.flush()
        return inserted_count

    @staticmethod
    def search_vector(
        db: Session,
        query_vector: list[float],
        top_k: int = 5,
        document_id: str | None = None,
    ) -> list[dict[str, Any]]:
        conditions = ["embedding IS NOT NULL"]
        if document_id:
            conditions.append("document_id = :doc_id")
        sql = text(
            f"""
            SELECT id, document_id, chunk_index, content, metadata_json,
                   1 - (embedding <=> CAST(:query_vec AS vector)) AS similarity_score
            FROM document_chunks
            WHERE {' AND '.join(conditions)}
            ORDER BY embedding <=> CAST(:query_vec AS vector)
            LIMIT :top_k
            """
        )
        params: dict[str, Any] = {"query_vec": str(query_vector), "top_k": top_k}
        if document_id:
            params["doc_id"] = document_id
        return VectorStoreRepository._serialize_rows(
            db.execute(sql, params).fetchall(), "similarity_score"
        )

    @staticmethod
    def search_hybrid(
        db: Session,
        query_text: str,
        query_vector: list[float],
        top_k: int = 5,
        document_id: str | None = None,
    ) -> list[dict[str, Any]]:
        vector_results = VectorStoreRepository.search_vector(
            db, query_vector, top_k=top_k * 2, document_id=document_id
        )
        filter_clause = "AND document_id = :doc_id" if document_id else ""
        sql = text(
            f"""
            SELECT id, document_id, chunk_index, content, metadata_json,
                   ts_rank_cd(to_tsvector('simple', content), plainto_tsquery('simple', :query)) AS fts_rank
            FROM document_chunks
            WHERE to_tsvector('simple', content) @@ plainto_tsquery('simple', :query)
            {filter_clause}
            ORDER BY fts_rank DESC
            LIMIT :top_k
            """
        )
        params: dict[str, Any] = {"query": query_text, "top_k": top_k * 2}
        if document_id:
            params["doc_id"] = document_id
        fts_results = VectorStoreRepository._serialize_rows(
            db.execute(sql, params).fetchall(), "fts_rank"
        )
        return VectorStoreRepository._fuse_results(vector_results, fts_results, top_k)

    @staticmethod
    def expand_neighbor_chunks(
        db: Session,
        seed_chunks: list[dict[str, Any]],
        neighbor_window: int = 1,
    ) -> list[dict[str, Any]]:
        """Load chunks surrounding each retrieved seed chunk."""
        if not seed_chunks:
            return []

        indexes_by_document: dict[str, set[int]] = {}
        document_order: list[str] = []
        seed_details: dict[tuple[str, int], tuple[int, float]] = {}

        for rank, chunk in enumerate(seed_chunks):
            document_id = chunk["document_id"]
            chunk_index = chunk["chunk_index"]
            if document_id not in indexes_by_document:
                indexes_by_document[document_id] = set()
                document_order.append(document_id)

            start_index = max(0, chunk_index - neighbor_window)
            end_index = chunk_index + neighbor_window
            indexes_by_document[document_id].update(range(start_index, end_index + 1))
            seed_details[(document_id, chunk_index)] = (rank, chunk["score"])

        expanded: list[dict[str, Any]] = []
        for document_position, document_id in enumerate(document_order):
            rows = (
                db.query(DocumentChunk)
                .filter(
                    DocumentChunk.document_id == document_id,
                    DocumentChunk.chunk_index.in_(indexes_by_document[document_id]),
                )
                .order_by(DocumentChunk.chunk_index)
                .all()
            )

            document_seeds = [
                (index, rank, score)
                for (seed_document_id, index), (rank, score) in seed_details.items()
                if seed_document_id == document_id
            ]
            for row in rows:
                nearest_index, nearest_rank, nearest_score = min(
                    document_seeds,
                    key=lambda seed: (abs(seed[0] - row.chunk_index), seed[1]),
                )
                is_seed = (document_id, row.chunk_index) in seed_details
                metadata = dict(row.metadata_json or {})
                metadata.update(
                    {
                        "is_neighbor": not is_seed,
                        "seed_chunk_index": nearest_index,
                    }
                )
                expanded.append(
                    {
                        "chunk_id": row.id,
                        "document_id": row.document_id,
                        "chunk_index": row.chunk_index,
                        "content": row.content,
                        "metadata": metadata,
                        "score": nearest_score,
                        "retrieval_rank": nearest_rank,
                        "document_rank": document_position,
                    }
                )

        return expanded

    @staticmethod
    def _serialize_rows(rows: Any, score_field: str) -> list[dict[str, Any]]:
        return [
            {
                "chunk_id": row.id,
                "document_id": row.document_id,
                "chunk_index": row.chunk_index,
                "content": row.content,
                "metadata": row.metadata_json,
                "score": float(getattr(row, score_field) or 0.0),
            }
            for row in rows
        ]

    @staticmethod
    def _fuse_results(
        vector_results: list[dict[str, Any]],
        fts_results: list[dict[str, Any]],
        top_k: int,
    ) -> list[dict[str, Any]]:
        scores: dict[str, float] = {}
        chunks: dict[str, dict[str, Any]] = {}
        for results in (vector_results, fts_results):
            for rank, item in enumerate(results, start=1):
                chunk_id = item["chunk_id"]
                chunks.setdefault(chunk_id, item)
                scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (60 + rank)

        if not scores:
            return vector_results[:top_k]
        result = []
        for chunk_id in sorted(scores, key=scores.get, reverse=True)[:top_k]:
            item = chunks[chunk_id].copy()
            item["score"] = scores[chunk_id]
            result.append(item)
        return result
