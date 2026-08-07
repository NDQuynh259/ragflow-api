"""Agent state definition for LangGraph (future implementation)."""
from typing import Any, TypedDict


class AgentState(TypedDict):
    """State for the agentic RAG graph."""
    query: str
    documents: list[Any]
    generation: str
    grade: str
    web_search_needed: bool
