from pydantic import BaseModel, Field
from typing import Any
from rag_document_pipeline import DocumentChunk

class RetrievedChunk(BaseModel):
    chunk: DocumentChunk
    score: float

class Citation(BaseModel):
    document_id: str
    chunk_id: str
    page_number: int
    bbox: tuple[float, float, float, float] | None = None

class RAGResponse(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    retrieved: list[RetrievedChunk] = Field(default_factory=list)

class RAGEngine:
    def index(self, chunks: list[DocumentChunk]) -> int:
        return len(chunks)
    def answer(self, query: str, chunks: list[DocumentChunk]) -> RAGResponse:
        matches = [c for c in chunks if any(word.lower() in c.content.lower() for word in query.split())][:5]
        if not matches: return RAGResponse(answer="Không tìm thấy thông tin phù hợp trong tài liệu.")
        return RAGResponse(answer=matches[0].content, retrieved=[RetrievedChunk(chunk=c, score=1.0) for c in matches])
