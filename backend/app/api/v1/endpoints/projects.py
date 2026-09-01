import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.models.paper import Paper
from app.models.project import Project
from app.models.project_paper import ProjectPaper
from app.schemas.project import (
    ProjectCreate,
    ProjectUpdate,
    ProjectResponse,
    ProjectPaperCreate,
    ProjectPaperUpdate,
    ProjectPaperResponse,
)
from app.schemas.paper import PaperResponse, CitationGraphData, ConceptGraphData
from app.schemas.reading_data import (
    ProjectPaperReadingData,
    NoteCreate, NoteUpdate, NoteResponse,
    HighlightCreate, HighlightUpdate, HighlightResponse,
    ReadingProgressUpdate, ReadingProgressResponse,
)
from app.models.saved_artifact import SavedArtifact
from app.schemas.saved_artifact import SavedArtifactCreate, SavedArtifactResponse
from app.services.project_service import project_service
from app.services.paper_service import paper_service
from app.services.reading_data_service import reading_data_service
from app.services.graph_service import graph_service

router = APIRouter()


# ────────────────────────── Projects CRUD ──────────────────────────

@router.get("/", response_model=list[ProjectResponse])
async def get_projects(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    return await project_service.get_projects_by_user(session=db, user_id=current_user.id)


@router.post("/", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    project_in: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    return await project_service.create_project(session=db, user_id=current_user.id, project_in=project_in)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    project = await project_service.get_project_by_id(session=db, project_id=project_id, user_id=current_user.id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: uuid.UUID,
    project_in: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    project = await project_service.get_project_by_id(session=db, project_id=project_id, user_id=current_user.id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return await project_service.update_project(session=db, db_project=project, project_in=project_in)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    project = await project_service.get_project_by_id(session=db, project_id=project_id, user_id=current_user.id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    await project_service.delete_project(session=db, db_project=project)
    return None


@router.get("/{project_id}/stats", response_model=dict)
async def get_project_stats(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    # Ensure the user has access to the project
    await project_service.get_project_by_id(session=db, project_id=project_id, user_id=current_user.id)
    
    # Get paper count
    stmt = select(func.count()).select_from(ProjectPaper).where(ProjectPaper.project_id == project_id)
    paper_count = await db.scalar(stmt)
    
    # Get note count
    from app.models.note import Note
    stmt2 = select(func.count()).select_from(Note).join(ProjectPaper).where(ProjectPaper.project_id == project_id)
    note_count = await db.scalar(stmt2)
    
    return {
        "total_papers": paper_count or 0,
        "total_notes": note_count or 0,
    }


# ────────────────────────── Project Papers ──────────────────────────

@router.get("/{project_id}/papers", response_model=list[PaperResponse])
async def get_project_papers(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    project = await project_service.get_project_by_id(session=db, project_id=project_id, user_id=current_user.id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    stmt = select(Paper).join(ProjectPaper).where(ProjectPaper.project_id == project_id)
    result = await db.scalars(stmt)
    return list(result.all())


@router.post("/{project_id}/papers", response_model=ProjectPaperResponse, status_code=status.HTTP_201_CREATED)
async def add_paper_to_project(
    project_id: uuid.UUID,
    project_paper_in: ProjectPaperCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    project = await project_service.get_project_by_id(session=db, project_id=project_id, user_id=current_user.id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    paper = await paper_service.get_paper_by_id(session=db, paper_id=project_paper_in.paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    existing = await project_service.get_project_paper(session=db, project_id=project_id, paper_id=project_paper_in.paper_id)
    if existing:
        raise HTTPException(status_code=400, detail="Paper already added to project")

    return await project_service.add_paper_to_project(session=db, project_id=project_id, project_paper_in=project_paper_in)


@router.patch("/{project_id}/papers/{paper_id}", response_model=ProjectPaperResponse)
async def update_project_paper(
    project_id: uuid.UUID,
    paper_id: uuid.UUID,
    project_paper_in: ProjectPaperUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    project = await project_service.get_project_by_id(session=db, project_id=project_id, user_id=current_user.id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    project_paper = await project_service.get_project_paper(session=db, project_id=project_id, paper_id=paper_id)
    if not project_paper:
        raise HTTPException(status_code=404, detail="Paper not found in project")

    return await project_service.update_project_paper(session=db, db_project_paper=project_paper, project_paper_in=project_paper_in)


@router.delete("/{project_id}/papers/{paper_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_paper_from_project(
    project_id: uuid.UUID,
    paper_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    project = await project_service.get_project_by_id(session=db, project_id=project_id, user_id=current_user.id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    project_paper = await project_service.get_project_paper(session=db, project_id=project_id, paper_id=paper_id)
    if not project_paper:
        raise HTTPException(status_code=404, detail="Paper not found in project")

    await project_service.remove_paper_from_project(session=db, db_project_paper=project_paper)
    return None


# ────────────────────────── Reading Data ──────────────────────────

async def _get_project_paper_or_404(
    db: AsyncSession,
    project_id: uuid.UUID,
    paper_id: uuid.UUID,
    user_id: uuid.UUID,
) -> ProjectPaper:
    """Load project_paper with all child collections eagerly (required for async)."""
    project = await project_service.get_project_by_id(session=db, project_id=project_id, user_id=user_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    stmt = (
        select(ProjectPaper)
        .where(ProjectPaper.project_id == project_id, ProjectPaper.paper_id == paper_id)
        .options(
            selectinload(ProjectPaper.notes),
            selectinload(ProjectPaper.highlights),
            selectinload(ProjectPaper.reading_progress),
        )
    )
    project_paper = await db.scalar(stmt)
    if not project_paper:
        raise HTTPException(status_code=404, detail="Paper not found in project")
    return project_paper


@router.get("/{project_id}/papers/{paper_id}/reading-data", response_model=ProjectPaperReadingData)
async def get_reading_data(
    project_id: uuid.UUID,
    paper_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    project_paper = await _get_project_paper_or_404(db, project_id, paper_id, current_user.id)
    return ProjectPaperReadingData(
        project_paper_id=project_paper.id,
        status=project_paper.status,
        favorite=project_paper.favorite,
        priority=project_paper.priority,
        added_at=project_paper.added_at,
        notes=project_paper.notes,
        highlights=project_paper.highlights,
        reading_progress=project_paper.reading_progress[0] if project_paper.reading_progress else None,
    )


# ── Notes ──

@router.post("/{project_id}/papers/{paper_id}/notes", response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
async def create_note(
    project_id: uuid.UUID,
    paper_id: uuid.UUID,
    note_in: NoteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    project_paper = await _get_project_paper_or_404(db, project_id, paper_id, current_user.id)
    return await reading_data_service.create_note(session=db, project_paper_id=project_paper.id, note_in=note_in)


@router.patch("/{project_id}/papers/{paper_id}/notes/{note_id}", response_model=NoteResponse)
async def update_note(
    project_id: uuid.UUID,
    paper_id: uuid.UUID,
    note_id: uuid.UUID,
    note_in: NoteUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    project_paper = await _get_project_paper_or_404(db, project_id, paper_id, current_user.id)
    db_note = await reading_data_service.get_note(session=db, note_id=note_id)
    if not db_note or db_note.project_paper_id != project_paper.id:
        raise HTTPException(status_code=404, detail="Note not found")
    return await reading_data_service.update_note(session=db, db_note=db_note, note_in=note_in)


@router.delete("/{project_id}/papers/{paper_id}/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    project_id: uuid.UUID,
    paper_id: uuid.UUID,
    note_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    project_paper = await _get_project_paper_or_404(db, project_id, paper_id, current_user.id)
    db_note = await reading_data_service.get_note(session=db, note_id=note_id)
    if not db_note or db_note.project_paper_id != project_paper.id:
        raise HTTPException(status_code=404, detail="Note not found")
    await reading_data_service.delete_note(session=db, db_note=db_note)
    return None


# ── Highlights ──

@router.post("/{project_id}/papers/{paper_id}/highlights", response_model=HighlightResponse, status_code=status.HTTP_201_CREATED)
async def create_highlight(
    project_id: uuid.UUID,
    paper_id: uuid.UUID,
    highlight_in: HighlightCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    project_paper = await _get_project_paper_or_404(db, project_id, paper_id, current_user.id)
    return await reading_data_service.create_highlight(session=db, project_paper_id=project_paper.id, highlight_in=highlight_in)


@router.patch("/{project_id}/papers/{paper_id}/highlights/{highlight_id}", response_model=HighlightResponse)
async def update_highlight(
    project_id: uuid.UUID,
    paper_id: uuid.UUID,
    highlight_id: uuid.UUID,
    highlight_in: HighlightUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    project_paper = await _get_project_paper_or_404(db, project_id, paper_id, current_user.id)
    db_hl = await reading_data_service.get_highlight(session=db, highlight_id=highlight_id)
    if not db_hl or db_hl.project_paper_id != project_paper.id:
        raise HTTPException(status_code=404, detail="Highlight not found")
    return await reading_data_service.update_highlight(session=db, db_hl=db_hl, highlight_in=highlight_in)


@router.delete("/{project_id}/papers/{paper_id}/highlights/{highlight_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_highlight(
    project_id: uuid.UUID,
    paper_id: uuid.UUID,
    highlight_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    project_paper = await _get_project_paper_or_404(db, project_id, paper_id, current_user.id)
    db_hl = await reading_data_service.get_highlight(session=db, highlight_id=highlight_id)
    if not db_hl or db_hl.project_paper_id != project_paper.id:
        raise HTTPException(status_code=404, detail="Highlight not found")
    await reading_data_service.delete_highlight(session=db, db_hl=db_hl)
    return None


# ── Reading Progress ──

@router.patch("/{project_id}/papers/{paper_id}/progress", response_model=ReadingProgressResponse)
async def upsert_reading_progress(
    project_id: uuid.UUID,
    paper_id: uuid.UUID,
    progress_in: ReadingProgressUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    project_paper = await _get_project_paper_or_404(db, project_id, paper_id, current_user.id)
    return await reading_data_service.upsert_reading_progress(
        session=db, project_paper_id=project_paper.id, progress_in=progress_in
    )


# -- Saved Artifacts --

async def _get_project_or_404(db: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID) -> Project:
    project = await project_service.get_project_by_id(session=db, project_id=project_id, user_id=user_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project

@router.get("/{project_id}/artifacts", response_model=list[SavedArtifactResponse])
async def get_project_artifacts(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    project = await _get_project_or_404(db, project_id, current_user.id)
    stmt = select(SavedArtifact).where(SavedArtifact.project_id == project_id, SavedArtifact.user_id == current_user.id).order_by(SavedArtifact.created_at.desc())
    result = await db.scalars(stmt)
    return list(result.all())

@router.post("/{project_id}/artifacts", response_model=SavedArtifactResponse, status_code=status.HTTP_201_CREATED)
async def create_artifact(
    project_id: uuid.UUID,
    artifact_in: SavedArtifactCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    project = await _get_project_or_404(db, project_id, current_user.id)
    
    # Check for duplicates
    stmt = select(SavedArtifact).where(
        SavedArtifact.project_id == project.id,
        SavedArtifact.user_id == current_user.id,
        SavedArtifact.artifact_type == artifact_in.artifact_type,
        SavedArtifact.content == artifact_in.content
    )
    existing = await db.scalar(stmt)
    if existing:
        # Return the existing artifact or raise 409 depending on preference
        # Returning existing with 200 is often nicer for frontend idempotency
        return existing
    
    artifact = SavedArtifact(
        project_id=project.id,
        user_id=current_user.id,
        paper_id=artifact_in.paper_id,
        artifact_type=artifact_in.artifact_type,
        title=artifact_in.title,
        content=artifact_in.content,
        cited_paper_ids=artifact_in.cited_paper_ids or []
    )
    db.add(artifact)
    await db.commit()
    await db.refresh(artifact)
    return artifact

@router.delete("/{project_id}/artifacts/{artifact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_artifact(
    project_id: uuid.UUID,
    artifact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    project = await _get_project_or_404(db, project_id, current_user.id)
    stmt = select(SavedArtifact).where(SavedArtifact.id == artifact_id, SavedArtifact.project_id == project_id)
    artifact = await db.scalar(stmt)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")
    
    
    await db.delete(artifact)
    await db.commit()
    return None

# ── Graphs ──

@router.get("/{project_id}/citation-graph", response_model=CitationGraphData)
async def get_project_citation_graph(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    # Ensure project access
    project = await _get_project_or_404(db, project_id, current_user.id)
    return await graph_service.get_project_citation_graph(session=db, project_id=project.id)

@router.get("/{project_id}/concept-graph", response_model=ConceptGraphData)
async def get_project_concept_graph(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    # Ensure project access
    project = await _get_project_or_404(db, project_id, current_user.id)
    return await graph_service.get_project_concept_graph(session=db, project_id=project.id)
