import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

class ProjectBase(BaseModel):
    name: str
    description: Optional[str] = None
    color: Optional[str] = None

class ProjectCreate(ProjectBase):
    pass

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None

class ProjectResponse(ProjectBase):
    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class ProjectPaperBase(BaseModel):
    status: Optional[str] = None
    favorite: bool = False
    priority: Optional[int] = None

class ProjectPaperCreate(ProjectPaperBase):
    paper_id: uuid.UUID

class ProjectPaperUpdate(BaseModel):
    status: Optional[str] = None
    favorite: Optional[bool] = None
    priority: Optional[int] = None

class ProjectPaperResponse(ProjectPaperBase):
    id: uuid.UUID
    project_id: uuid.UUID
    paper_id: uuid.UUID
    added_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
