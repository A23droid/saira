import uuid
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from .paper import PaperResponse

class CitationResponse(BaseModel):
    id: str
    title: str
    year: Optional[int] = None
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    semantic_scholar_id: Optional[str] = None
    has_pdf: Optional[bool] = None

class DependencyResponse(BaseModel):
    id: str
    name: str
    type: str
    rel_props: Optional[Dict[str, Any]] = None

class GraphCitationsResponse(BaseModel):
    citations: List[CitationResponse]
    references: List[CitationResponse]

class ConceptNodeResponse(BaseModel):
    id: str
    label: str
    type: str

class ConceptEdgeResponse(BaseModel):
    source: str
    target: str
    label: str

class GraphConceptsResponse(BaseModel):
    nodes: List[ConceptNodeResponse]
    edges: List[ConceptEdgeResponse]

class ResearchMapResponse(BaseModel):
    paper: PaperResponse
    citations: List[CitationResponse]
    dependencies: List[DependencyResponse]
    similar: List[PaperResponse]
