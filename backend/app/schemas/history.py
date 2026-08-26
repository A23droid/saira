from pydantic import BaseModel, Field
import uuid
from datetime import datetime
from typing import Optional, Any, Dict

class HistoryEventCreate(BaseModel):
    event_type: str
    reference_id: Optional[str] = None
    metadata_json: Optional[Dict[str, Any]] = None
    title: Optional[str] = None
    url: Optional[str] = None
    description: Optional[str] = None

class HistoryEventResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    event_type: str
    reference_id: Optional[str] = None
    metadata_json: Optional[Dict[str, Any]] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

class FrontendHistoryEvent(BaseModel):
    id: str
    type: str
    timestamp: str
    title: str
    description: Optional[str] = None
    url: Optional[str] = None
