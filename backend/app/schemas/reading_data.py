import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict

# Notes
class NoteBase(BaseModel):
    title: Optional[str] = None
    content: str

class NoteCreate(NoteBase):
    pass

class NoteUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None

class NoteResponse(NoteBase):
    id: uuid.UUID
    project_paper_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

# Highlights
class HighlightBase(BaseModel):
    page: Optional[int] = None
    selected_text: str
    ai_note: Optional[str] = None

class HighlightCreate(HighlightBase):
    pass

class HighlightUpdate(BaseModel):
    page: Optional[int] = None
    selected_text: Optional[str] = None
    ai_note: Optional[str] = None

class HighlightResponse(HighlightBase):
    id: uuid.UUID
    project_paper_id: uuid.UUID
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

# Reading Progress
class ReadingProgressBase(BaseModel):
    progress_percent: int
    last_page: Optional[int] = None
    started_at: Optional[datetime] = None
    last_opened: Optional[datetime] = None
    completed_at: Optional[datetime] = None

class ReadingProgressCreate(ReadingProgressBase):
    pass

class ReadingProgressUpdate(BaseModel):
    progress_percent: Optional[int] = None
    last_page: Optional[int] = None
    started_at: Optional[datetime] = None
    last_opened: Optional[datetime] = None
    completed_at: Optional[datetime] = None

class ReadingProgressResponse(ReadingProgressBase):
    id: uuid.UUID
    project_paper_id: uuid.UUID
    
    model_config = ConfigDict(from_attributes=True)

# Aggregated Reading Data (Returned for a project context)
class ProjectPaperReadingData(BaseModel):
    project_paper_id: uuid.UUID
    status: Optional[str] = None
    favorite: bool = False
    priority: Optional[int] = None
    added_at: datetime
    notes: list[NoteResponse]
    highlights: list[HighlightResponse]
    reading_progress: Optional[ReadingProgressResponse] = None
