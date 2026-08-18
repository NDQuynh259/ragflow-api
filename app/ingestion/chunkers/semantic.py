"""Semantic chunking for text blocks emitted by the PDF layout parser."""
from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter


class SemanticChunker:
    """Split text into semantic chunks."""
    def split(self, text: str, chunk_size: int = 1200, chunk_overlap: int = 200) -> list[dict[str, Any]]:
        if chunk_size <= 0 or chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be non-negative and smaller than chunk_size")
        if not text or not text.strip():
            return []
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
        )
        return [
            {"chunk_index": index, "content": chunk}
            for index, chunk in enumerate(splitter.split_text(text))
        ]
