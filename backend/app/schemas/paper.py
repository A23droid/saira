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
    local_id: Optional[str] = None
    saved_project_ids: list[str] = []

class CitationGraphNode(BaseModel):
    id: str
    label: str
    year: Optional[int] = None
    group: int  # 1=target, 2=cited, 3=citing

class CitationGraphEdge(BaseModel):
    source: str
    target: str

class CitationGraphData(BaseModel):
    nodes: list[CitationGraphNode]
    edges: list[CitationGraphEdge]

class ConceptGraphNode(BaseModel):
    id: str
    label: str
    type: str  # e.g., 'task', 'method', 'dataset', 'metric'

class ConceptGraphEdge(BaseModel):
    source: str
    target: str
    label: str

class ConceptGraphData(BaseModel):
    nodes: list[ConceptGraphNode]
    edges: list[ConceptGraphEdge]

