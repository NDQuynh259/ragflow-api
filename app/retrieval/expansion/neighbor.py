"""Neighbor node expansion - load surrounding nodes for richer context."""
from typing import Any
from sqlalchemy.orm import Session
from app.domain.document_node import DocumentNode


def expand_neighbor_nodes(db: Session, seed_nodes: list[dict[str, Any]],
                           neighbor_window: int = 1) -> list[dict[str, Any]]:
    """Load nodes surrounding each retrieved seed node."""
    if not seed_nodes:
        return []

    indexes_by_document: dict[str, set[int]] = {}
    document_order: list[str] = []
    seed_details: dict[tuple[str, int], tuple[int, float]] = {}

    for rank, node in enumerate(seed_nodes):
        document_id = node["document_id"]
        node_index = node["chunk_index"]
        if document_id not in indexes_by_document:
            indexes_by_document[document_id] = set()
            document_order.append(document_id)
        start_index = max(0, node_index - neighbor_window)
        end_index = node_index + neighbor_window
        indexes_by_document[document_id].update(range(start_index, end_index + 1))
        seed_details[(document_id, node_index)] = (rank, node["score"])

    expanded: list[dict[str, Any]] = []
    for document_position, document_id in enumerate(document_order):
        rows = (db.query(DocumentNode)
                .filter(DocumentNode.document_id == document_id,
                        DocumentNode.node_index.in_(indexes_by_document[document_id]))
                .order_by(DocumentNode.node_index)
                .all())
        document_seeds = [(index, rank, score)
                          for (seed_document_id, index), (rank, score) in seed_details.items()
                          if seed_document_id == document_id]
        for row in rows:
            nearest_index, nearest_rank, nearest_score = min(
                document_seeds, key=lambda seed: (abs(seed[0] - row.node_index), seed[1]))
            is_seed = (document_id, row.node_index) in seed_details
            metadata = dict(row.metadata_json or {})
            metadata.update({"is_neighbor": not is_seed, "seed_chunk_index": nearest_index})
            expanded.append({
                "chunk_id": row.id, "document_id": row.document_id,
                "chunk_index": row.node_index, "content": row.content,
                "metadata": metadata, "score": nearest_score,
                "retrieval_rank": nearest_rank, "document_rank": document_position,
            })
    return expanded
