import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.models.project import Project
from app.models.project_paper import ProjectPaper
from app.schemas.paper import PaperCreate, PaperUpdate, PaperResponse
from app.schemas.project import ProjectResponse
from app.services.paper_service import paper_service

router = APIRouter()


@router.get("/", response_model=list[PaperResponse])
async def get_papers(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    return await paper_service.get_all_papers(session=db, skip=skip, limit=limit)


@router.post("/", response_model=PaperResponse, status_code=status.HTTP_201_CREATED)
async def create_paper(
    paper_in: PaperCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    return await paper_service.create_paper(session=db, paper_in=paper_in)


@router.get("/{paper_id}", response_model=PaperResponse)
async def get_paper(
    paper_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    paper = await paper_service.get_paper_by_id(session=db, paper_id=paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    return paper


@router.patch("/{paper_id}", response_model=PaperResponse)
async def update_paper(
    paper_id: uuid.UUID,
    paper_in: PaperUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    paper = await paper_service.get_paper_by_id(session=db, paper_id=paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    return await paper_service.update_paper(session=db, db_paper=paper, paper_in=paper_in)


@router.delete("/{paper_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_paper(
    paper_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    paper = await paper_service.get_paper_by_id(session=db, paper_id=paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    await paper_service.delete_paper(session=db, db_paper=paper)
    return None


@router.get("/{paper_id}/projects", response_model=list[ProjectResponse])
async def get_paper_projects(
    paper_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    stmt = (
        select(Project)
        .join(ProjectPaper)
        .where(ProjectPaper.paper_id == paper_id, Project.user_id == current_user.id)
    )
    result = await db.scalars(stmt)
    return list(result.all())
