import uuid
from fastapi import APIRouter, File, HTTPException, UploadFile
from rag_document_pipeline import DocumentPipeline
from rag_core import RAGEngine
from chat_api.api.schemas.chat import MessageCreate, MessageResponse, SessionCreate, SessionResponse

router = APIRouter()
sessions: dict[str, dict] = {}

@router.post("/sessions", response_model=SessionResponse)
def create_session(payload: SessionCreate):
    sid = str(uuid.uuid4()); sessions[sid] = {"title": payload.title, "documents": [], "chunks": []}
    return {"id": sid, "title": payload.title, "document_ids": []}

@router.post("/sessions/{session_id}/documents")
def upload(session_id: str, file: UploadFile = File(...)):
    session = sessions.get(session_id)
    if not session: raise HTTPException(404, "Session not found")
    content = file.file.read()
    doc_id = str(uuid.uuid4())
    processed = DocumentPipeline().process(content, filename=file.filename or "document.txt", document_id=doc_id)
    session["documents"].append(doc_id); session["chunks"].extend(processed.chunks)
    return {"document_id": doc_id, "filename": file.filename, "chunks": len(processed.chunks), "status": "ready"}

@router.post("/sessions/{session_id}/messages", response_model=MessageResponse)
def message(session_id: str, payload: MessageCreate):
    session = sessions.get(session_id)
    if not session: raise HTTPException(404, "Session not found")
    result = RAGEngine().answer(payload.content, session["chunks"])
    return {"answer": result.answer, "citations": [c.model_dump() for c in result.citations]}
