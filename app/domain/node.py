"""Node domain entity for graph-based RAG (LangGraph)."""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Node:
    """A node in the agentic RAG graph."""
    id: str
    type: str
    data: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
