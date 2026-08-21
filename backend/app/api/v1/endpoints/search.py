from typing import Any, List, Literal, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.models.project import Project
from app.schemas.paper import PaperSearchResponse
from app.schemas.project import ProjectPaperResponse
from app.schemas.paper import PaperResponse
from app.services.search_service import search_service, SearchSource

router = APIRouter()


class IngestRequest(BaseModel):
    # Source routing — exactly one ID field must be provided
    openalex_id: Optional[str] = None
    arxiv_id: Optional[str] = None
    semantic_scholar_id: Optional[str] = None
    # Optional project to add the paper to
    project_id: Optional[uuid.UUID] = None


class IngestResponse(BaseModel):
    paper: PaperResponse
    project_paper: Optional[ProjectPaperResponse] = None


@router.get("/", response_model=List[PaperSearchResponse])
async def search_papers(
    q: str,
    limit: int = Query(default=20, ge=1, le=100),
    page: int = Query(default=1, ge=1),
    source: SearchSource = Query(default="openalex"),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Search external paper sources.

    `source` can be: `openalex` | `arxiv` | `semantic_scholar` | `all`

    Results are normalized to the same schema regardless of source.
    They are NOT persisted — call POST /search/ingest to save a paper.
    """
    try:
        return await search_service.search_papers_external(query=q, limit=limit, page=page, source=source)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"External search failed: {str(e)}")


@router.post("/ingest", response_model=IngestResponse, status_code=status.HTTP_201_CREATED)
async def ingest_paper(
    req: IngestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """
    Ingest a paper from an external source into the database.

    Provide exactly one of: `openalex_id`, `arxiv_id`, `semantic_scholar_id`.
    Optionally provide `project_id` to also add the paper to a project.

    Deduplicates by DOI → arXiv ID → Semantic Scholar ID.
    """
    if not any([req.openalex_id, req.arxiv_id, req.semantic_scholar_id]):
        raise HTTPException(
            status_code=422,
            detail="Provide exactly one of: openalex_id, arxiv_id, semantic_scholar_id",
        )

    # Security: if a project_id is supplied, verify the current user owns it.
    if req.project_id:
        stmt = select(Project).where(
            Project.id == req.project_id,
            Project.user_id == current_user.id,
        )
        project = await db.scalar(stmt)
        if not project:
            raise HTTPException(
                status_code=404,
                detail="Project not found or does not belong to you",
            )

    try:
        result = await search_service.ingest_paper(
            session=db,
            project_id=req.project_id,
            openalex_id=req.openalex_id,
            arxiv_id=req.arxiv_id,
            semantic_scholar_id=req.semantic_scholar_id,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Ingestion failed: {str(e)}")
