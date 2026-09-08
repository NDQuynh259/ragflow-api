from pydantic import BaseModel, Field
class SessionCreate(BaseModel): title: str = "New chat"
class SessionResponse(BaseModel): id: str; title: str; document_ids: list[str] = Field(default_factory=list)
class MessageCreate(BaseModel): content: str = Field(min_length=1)
class MessageResponse(BaseModel): answer: str; citations: list[dict] = Field(default_factory=list)
