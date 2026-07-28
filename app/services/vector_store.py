from typing import List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.models import DocumentChunk
from app.config import settings

class VectorStoreService:
    @staticmethod
    def add_chunks(db: Session, chunks_data: List[Dict[str, Any]]) -> int:
        """Bulk insert chunks into PostgreSQL with pgvector embeddings."""
        inserted_count = 0
        for c in chunks_data:
            chunk_obj = DocumentChunk(
                document_id=c["document_id"],
                chunk_index=c["chunk_index"],
                content=c["content"],
                metadata_json=c.get("metadata", {}),
                embedding=c["embedding"]
            )
            db.add(chunk_obj)
            inserted_count += 1

            if inserted_count % settings.DB_INSERT_BATCH_SIZE == 0:
                db.flush()

        if inserted_count % settings.DB_INSERT_BATCH_SIZE:
            db.flush()
        return inserted_count

    @staticmethod
    def search_vector(
        db: Session, 
        query_vector: List[float], 
        top_k: int = 5,
        document_id: str = None
    ) -> List[Dict[str, Any]]:
        """
        Cosine similarity search using pgvector (<=> operator).
        Returns top-k matching chunks with similarity score.
        """
        # Formulate query
        conditions = ["embedding IS NOT NULL"]
        if document_id:
            conditions.append("document_id = :doc_id")
        filter_clause = "WHERE " + " AND ".join(conditions)
        
        sql = text(f"""
            SELECT 
                id, document_id, chunk_index, content, metadata_json,
                1 - (embedding <=> CAST(:query_vec AS vector)) AS similarity_score
            FROM document_chunks
            {filter_clause}
            ORDER BY embedding <=> CAST(:query_vec AS vector)
            LIMIT :top_k
        """)

        params = {"query_vec": str(query_vector), "top_k": top_k}
        if document_id:
            params["doc_id"] = document_id

        result = db.execute(sql, params)
        rows = result.fetchall()

        output = []
        for r in rows:
            output.append({
                "chunk_id": r.id,
                "document_id": r.document_id,
                "chunk_index": r.chunk_index,
                "content": r.content,
                "metadata": r.metadata_json,
                "score": float(r.similarity_score) if r.similarity_score else 0.0
            })
        return output

    @staticmethod
    def search_hybrid(
        db: Session,
        query_text: str,
        query_vector: List[float],
        top_k: int = 5,
        document_id: str = None,
    ) -> List[Dict[str, Any]]:
        """
        Hybrid Search combining vector search and PostgreSQL full-text ranking.
        Uses Reciprocal Rank Fusion (RRF) to merge rankings.
        """
        # 1. Fetch Top-K from Vector Search
        vector_results = VectorStoreService.search_vector(
            db,
            query_vector,
            top_k=top_k * 2,
            document_id=document_id,
        )

        # 2. Fetch Top-K from PostgreSQL Full-Text Search
        filter_clause = "AND document_id = :doc_id" if document_id else ""
        sql_fts = text("""
            SELECT id, document_id, chunk_index, content, metadata_json,
                   ts_rank_cd(to_tsvector('simple', content), plainto_tsquery('simple', :query)) as fts_rank
            FROM document_chunks
            WHERE to_tsvector('simple', content) @@ plainto_tsquery('simple', :query)
            {filter_clause}
            ORDER BY fts_rank DESC
            LIMIT :top_k
        """.format(filter_clause=filter_clause))
        params = {"query": query_text, "top_k": top_k * 2}
        if document_id:
            params["doc_id"] = document_id
        fts_rows = db.execute(sql_fts, params).fetchall()
        fts_results = []
        for r in fts_rows:
            fts_results.append({
                "chunk_id": r.id,
                "document_id": r.document_id,
                "chunk_index": r.chunk_index,
                "content": r.content,
                "metadata": r.metadata_json,
                "score": float(r.fts_rank)
            })

        # 3. Reciprocal Rank Fusion (RRF)
        rrf_scores = {}
        chunk_map = {}
        k_constant = 60

        for rank, item in enumerate(vector_results):
            cid = item["chunk_id"]
            chunk_map[cid] = item
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (k_constant + rank + 1))

        for rank, item in enumerate(fts_results):
            cid = item["chunk_id"]
            if cid not in chunk_map:
                chunk_map[cid] = item
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (k_constant + rank + 1))

        # Sort by RRF score
        sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)[:top_k]
        
        final_results = []
        for cid in sorted_ids:
            res = chunk_map[cid]
            res["score"] = rrf_scores[cid]
            final_results.append(res)

        # Fallback to vector_results if FTS returned nothing
        if not final_results:
            return vector_results[:top_k]

        return final_results
