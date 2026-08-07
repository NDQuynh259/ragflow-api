"""RetrievalResult domain entity."""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RetrievalResult:
    chunk_id: str
    document_id: str
    chunk_index: int
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    retrieval_rank: int = 0
