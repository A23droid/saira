import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict

class PaperBase(BaseModel):
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    semantic_scholar_id: Optional[str] = None
    title: str
    abstract: Optional[str] = None
    publication_year: Optional[int] = None
    venue: Optional[str] = None
    pdf_url: Optional[str] = None
    source: Optional[str] = None
    citation_count: Optional[int] = None
    reference_count: Optional[int] = None

class PaperCreate(PaperBase):
    pass

class PaperUpdate(BaseModel):
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    semantic_scholar_id: Optional[str] = None
    title: Optional[str] = None
    abstract: Optional[str] = None
    publication_year: Optional[int] = None
    venue: Optional[str] = None
    pdf_url: Optional[str] = None
    source: Optional[str] = None
    citation_count: Optional[int] = None
    reference_count: Optional[int] = None

class PaperResponse(PaperBase):
    id: uuid.UUID
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class PaperSearchResponse(PaperBase):
    openalex_id: Optional[str] = None

