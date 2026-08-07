"""Neighbor chunk expansion - load surrounding chunks for richer context."""
from typing import Any
from sqlalchemy.orm import Session
from app.domain.chunk import DocumentChunk


def expand_neighbor_chunks(db: Session, seed_chunks: list[dict[str, Any]],
                           neighbor_window: int = 1) -> list[dict[str, Any]]:
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
        rows = (db.query(DocumentChunk)
                .filter(DocumentChunk.document_id == document_id,
                        DocumentChunk.chunk_index.in_(indexes_by_document[document_id]))
                .order_by(DocumentChunk.chunk_index)
                .all())
        document_seeds = [(index, rank, score)
                          for (seed_document_id, index), (rank, score) in seed_details.items()
                          if seed_document_id == document_id]
        for row in rows:
            nearest_index, nearest_rank, nearest_score = min(
                document_seeds, key=lambda seed: (abs(seed[0] - row.chunk_index), seed[1]))
            is_seed = (document_id, row.chunk_index) in seed_details
            metadata = dict(row.metadata_json or {})
            metadata.update({"is_neighbor": not is_seed, "seed_chunk_index": nearest_index})
            expanded.append({
                "chunk_id": row.id, "document_id": row.document_id,
                "chunk_index": row.chunk_index, "content": row.content,
                "metadata": metadata, "score": nearest_score,
                "retrieval_rank": nearest_rank, "document_rank": document_position,
            })
    return expanded
