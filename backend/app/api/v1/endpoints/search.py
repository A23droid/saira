from typing import Any, List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.schemas.paper import PaperCreate, PaperResponse, PaperSearchResponse
from app.schemas.project import ProjectPaperResponse
from app.services.search_service import search_service

router = APIRouter()


class IngestRequest(BaseModel):
    openalex_id: str
    project_id: Optional[uuid.UUID] = None


class IngestResponse(BaseModel):
    paper: PaperResponse
    project_paper: Optional[ProjectPaperResponse] = None


@router.get("/", response_model=List[PaperSearchResponse])
async def search_papers(
    q: str,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
) -> Any:
    """Search OpenAlex and return normalized but un-persisted results."""
    try:
        return await search_service.search_papers_external(query=q, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.post("/ingest", response_model=IngestResponse, status_code=status.HTTP_201_CREATED)
async def ingest_paper(
    req: IngestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Ingest a paper by OpenAlex ID. Optionally adds it to a project.
    Deduplicates based on DOI / ArXiv ID.
    """
    try:
        result = await search_service.ingest_paper(
            session=db,
            openalex_id=req.openalex_id,
            project_id=req.project_id,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")
