import uuid
from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, ConfigDict

class SavedArtifactBase(BaseModel):
    artifact_type: Literal["chat_answer", "review_snippet"]
    title: str
    content: str
    cited_paper_ids: Optional[list[str]] = []

class SavedArtifactCreate(SavedArtifactBase):
    paper_id: Optional[uuid.UUID] = None

class SavedArtifactResponse(SavedArtifactBase):
    id: uuid.UUID
    project_id: Optional[uuid.UUID] = None
    paper_id: Optional[uuid.UUID] = None
    user_id: uuid.UUID
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
