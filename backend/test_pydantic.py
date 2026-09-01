import uuid
from typing import List
from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional

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

class PaperResponse(PaperBase):
    id: uuid.UUID
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

# Simulate what search_service returns
similar_candidates = [
    {
        "doi": "10.1234/test",
        "title": "Test Paper",
        "provider": "openalex"
    }
]

# Simulate what FastAPI does
try:
    from pydantic import TypeAdapter
    ta = TypeAdapter(List[PaperResponse])
    res = ta.validate_python(similar_candidates)
    print("Success:", res)
except Exception as e:
    print("Error:", type(e).__name__, e)
