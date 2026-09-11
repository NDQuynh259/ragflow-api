"""PostgreSQL + pgvector implementation of VectorStore."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from rag_contracts.chunks import ChunkRecord, SearchResult

logger = logging.getLogger(__name__)


class PgVectorStore:
    """Vector store backed by PostgreSQL with the pgvector extension.

    Table schema::

        chunks (
            id              TEXT PRIMARY KEY,
            document_id     TEXT NOT NULL,
            content         TEXT NOT NULL,
            embedding       vector(N),
            kind            TEXT DEFAULT 'text',
            page_start      INTEGER DEFAULT 1,
            page_end        INTEGER DEFAULT 1,
            element_ids     JSONB DEFAULT '[]',
            bboxes          JSONB DEFAULT '[]',
            section_path    JSONB DEFAULT '[]',
            token_count     INTEGER DEFAULT 0,
            indexable       BOOLEAN DEFAULT TRUE,
            metadata        JSONB DEFAULT '{}'
        )
    """

    def __init__(
        self,
        *,
        connection_url: str | None = None,
        embedding_dimension: int | None = None,
        table_name: str = "chunks",
    ) -> None:
        self._url = connection_url or os.environ.get(
            "DATABASE_URL",
            "postgresql+psycopg://postgres:postgrespassword@localhost:45432/rag_db",
        )
        # psycopg needs postgresql:// not postgresql+psycopg://
        self._dsn = self._url.replace("postgresql+psycopg://", "postgresql://")
        self._dim = embedding_dimension or int(
            os.environ.get("EMBEDDING_DIMENSION", "768")
        )
        self._table = table_name
        self._conn = None

    def _get_conn(self):
        """Lazy connection creation."""
        if self._conn is None or self._conn.closed:
            import psycopg

            self._conn = psycopg.connect(self._dsn, autocommit=True)
        return self._conn

    def ensure_schema(self) -> None:
        """Create the pgvector extension and chunks table if missing."""
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {self._table} (
                    id              TEXT PRIMARY KEY,
                    document_id     TEXT NOT NULL,
                    content         TEXT NOT NULL,
                    embedding       vector({self._dim}),
                    kind            TEXT DEFAULT 'text',
                    page_start      INTEGER DEFAULT 1,
                    page_end        INTEGER DEFAULT 1,
                    element_ids     JSONB DEFAULT '[]'::jsonb,
                    bboxes          JSONB DEFAULT '[]'::jsonb,
                    section_path    JSONB DEFAULT '[]'::jsonb,
                    token_count     INTEGER DEFAULT 0,
                    indexable       BOOLEAN DEFAULT TRUE,
                    metadata        JSONB DEFAULT '{{}}'::jsonb
                )
            """)
            # Create indexes
            cur.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{self._table}_document_id
                ON {self._table} (document_id)
            """)
            cur.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{self._table}_kind
                ON {self._table} (kind)
            """)
            # HNSW index for fast approximate nearest neighbor
            cur.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{self._table}_embedding_hnsw
                ON {self._table}
                USING hnsw (embedding vector_cosine_ops)
                WITH (m = 16, ef_construction = 64)
            """)
        logger.info("Schema ensured for table '%s'", self._table)

    def upsert(self, records: list[ChunkRecord]) -> int:
        """Insert or update chunk records."""
        if not records:
            return 0

        conn = self._get_conn()
        batch_size = int(os.environ.get("DB_INSERT_BATCH_SIZE", "100"))
        total = 0

        for i in range(0, len(records), batch_size):
            batch = records[i : i + batch_size]
            with conn.cursor() as cur:
                for rec in batch:
                    cur.execute(
                        f"""
                        INSERT INTO {self._table}
                            (id, document_id, content, embedding, kind,
                             page_start, page_end, element_ids, bboxes,
                             section_path, token_count, indexable, metadata)
                        VALUES
                            (%s, %s, %s, %s, %s,
                             %s, %s, %s, %s,
                             %s, %s, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET
                            content = EXCLUDED.content,
                            embedding = EXCLUDED.embedding,
                            kind = EXCLUDED.kind,
                            page_start = EXCLUDED.page_start,
                            page_end = EXCLUDED.page_end,
                            element_ids = EXCLUDED.element_ids,
                            bboxes = EXCLUDED.bboxes,
                            section_path = EXCLUDED.section_path,
                            token_count = EXCLUDED.token_count,
                            indexable = EXCLUDED.indexable,
                            metadata = EXCLUDED.metadata
                        """,
                        (
                            rec.id,
                            rec.document_id,
                            rec.content,
                            _vec_literal(rec.embedding),
                            rec.kind,
                            rec.page_start,
                            rec.page_end,
                            json.dumps(rec.element_ids),
                            json.dumps(
                                [list(b) for b in rec.bboxes]
                            ),
                            json.dumps(rec.section_path),
                            rec.token_count,
                            rec.indexable,
                            json.dumps(rec.metadata),
                        ),
                    )
                total += len(batch)

        logger.info("Upserted %d records into '%s'", total, self._table)
        return total

    def search(
        self,
        vector: list[float],
        *,
        top_k: int = 5,
        filter: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Cosine similarity search with optional metadata filtering."""
        conn = self._get_conn()

        where_clauses = ["indexable = TRUE"]
        params: list[Any] = [_vec_literal(vector), top_k]

        if filter:
            if "document_ids" in filter:
                doc_ids = filter["document_ids"]
                placeholders = ", ".join(["%s"] * len(doc_ids))
                where_clauses.append(
                    f"document_id IN ({placeholders})"
                )
                params = [_vec_literal(vector)] + list(doc_ids) + [top_k]
            if "kind" in filter:
                where_clauses.append("kind = %s")
                params.insert(-1, filter["kind"])

        where = " AND ".join(where_clauses)

        query = f"""
            SELECT id, document_id, content, kind,
                   page_start, page_end, element_ids, bboxes,
                   section_path, token_count, indexable, metadata,
                   1 - (embedding <=> %s) AS score
            FROM {self._table}
            WHERE {where}
            ORDER BY embedding <=> %s
            LIMIT %s
        """
        # We need the vector twice: once for score, once for ORDER BY
        final_params = [_vec_literal(vector)]
        if filter and "document_ids" in filter:
            final_params.extend(filter["document_ids"])
        if filter and "kind" in filter:
            final_params.append(filter["kind"])
        final_params.append(_vec_literal(vector))
        final_params.append(top_k)

        results: list[SearchResult] = []
        with conn.cursor() as cur:
            cur.execute(query, final_params)
            for row in cur.fetchall():
                (
                    id_,
                    doc_id,
                    content,
                    kind,
                    p_start,
                    p_end,
                    el_ids,
                    bboxes_json,
                    sec_path,
                    tok_count,
                    indexable,
                    meta,
                    score,
                ) = row
                chunk = ChunkRecord(
                    id=id_,
                    document_id=doc_id,
                    content=content,
                    kind=kind,
                    page_start=p_start,
                    page_end=p_end,
                    element_ids=el_ids if isinstance(el_ids, list) else json.loads(el_ids or "[]"),
                    bboxes=[tuple(b) for b in (bboxes_json if isinstance(bboxes_json, list) else json.loads(bboxes_json or "[]"))],
                    section_path=sec_path if isinstance(sec_path, list) else json.loads(sec_path or "[]"),
                    token_count=tok_count,
                    indexable=indexable,
                    metadata=meta if isinstance(meta, dict) else json.loads(meta or "{}"),
                )
                results.append(SearchResult(chunk=chunk, score=float(score)))

        return results

    def delete_by_document(self, document_id: str) -> int:
        """Delete all chunks for a document."""
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                f"DELETE FROM {self._table} WHERE document_id = %s",
                (document_id,),
            )
            deleted = cur.rowcount
        logger.info(
            "Deleted %d records for document '%s'", deleted, document_id
        )
        return deleted

    def close(self) -> None:
        """Close the database connection."""
        if self._conn and not self._conn.closed:
            self._conn.close()


def _vec_literal(vector: list[float]) -> str:
    """Format a vector as a pgvector literal string '[1,2,3]'."""
    return "[" + ",".join(str(v) for v in vector) + "]"
