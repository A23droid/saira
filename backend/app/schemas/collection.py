import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict

class CollectionBase(BaseModel):
    name: str
    description: Optional[str] = None
    color: Optional[str] = None

class CollectionCreate(CollectionBase):
    pass

class CollectionUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None

class CollectionResponse(CollectionBase):
    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class CollectionPaperResponse(BaseModel):
    id: uuid.UUID
    collection_id: uuid.UUID
    paper_id: uuid.UUID
    added_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
