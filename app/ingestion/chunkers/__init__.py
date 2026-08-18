"""Text chunking used by layout-aware PDF ingestion."""
from app.ingestion.chunkers.semantic import SemanticChunker

__all__ = ["SemanticChunker"]
