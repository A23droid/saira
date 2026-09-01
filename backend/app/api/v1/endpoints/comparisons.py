import uuid
from typing import Any
import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.models.paper import Paper
from app.models.comparison import Comparison, ComparisonPaper
from app.services.ai_router import ai_router

router = APIRouter()


class GenerateComparisonRequest(BaseModel):
    title: str
    paper_ids: list[str]
    project_id: str | None = None


def _paper_with_analysis_to_dict(paper: Paper, analysis=None) -> dict:
    """Convert a Paper ORM model (with analysis) to a dict for the AI layer."""
    data = {
        "title": paper.title,
        "abstract": paper.abstract,
        "publication_year": paper.publication_year,
        "venue": paper.venue,
        "source": paper.source,
        "doi": paper.doi,
        "arxiv_id": paper.arxiv_id,
        "semantic_scholar_id": paper.semantic_scholar_id,
        "citation_count": paper.citation_count,
        "reference_count": paper.reference_count,
    }
    
    # Add extracted analysis if available
    if analysis:
        parts = []
        if analysis.summary_researcher:
            parts.append(f"AI Summary: {analysis.summary_researcher}")
        elif analysis.summary_student:
            parts.append(f"AI Summary: {analysis.summary_student}")
        if analysis.datasets:
            parts.append(f"Datasets: {analysis.datasets}")
        if analysis.models:
            parts.append(f"Models: {analysis.models}")
        if analysis.algorithms:
            parts.append(f"Algorithms: {analysis.algorithms}")
        if analysis.results:
            parts.append(f"Results: {analysis.results}")
        if analysis.limitations:
            parts.append(f"Limitations: {analysis.limitations}")
        if analysis.future_work:
            parts.append(f"Future Work: {analysis.future_work}")
        if analysis.research_gap:
            parts.append(f"Research Gap: {analysis.research_gap}")
        if analysis.novelty:
            parts.append(f"Novelty: {analysis.novelty}")
        
        if parts:
            data["extra"] = "\n".join(parts)
            
    return data


@router.post("/generate")
async def generate_comparison(
    request: GenerateComparisonRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Generate a new structured comparison between multiple papers."""
    if len(request.paper_ids) < 2:
        raise HTTPException(status_code=400, detail="At least two papers are required for comparison.")
    if len(request.paper_ids) > 5:
        raise HTTPException(status_code=400, detail="Maximum 5 papers allowed for comparison.")
    
    # Fetch papers and their analysis if present
    # Using string 'analysis' for relation since it's defined on Paper as a backref or similar. Let's check `PaperAnalysis`
    # We will just fetch papers. If we need analysis, we should use selectinload(Paper.analysis) if it exists, otherwise just fetch papers.
    # To be safe from relationship naming issues, let's fetch PaperAnalysis explicitly for these papers if the relationship doesn't exist.
    # Actually, we can fetch papers first.
    stmt = select(Paper).where(Paper.id.in_(request.paper_ids))
    result = await db.execute(stmt)
    papers = result.scalars().all()
    
    if len(papers) != len(request.paper_ids):
        raise HTTPException(status_code=404, detail="One or more papers not found.")
    
    # We will fetch PaperAnalysis separately to avoid relationship name guesswork
    from app.models.paper_analysis import PaperAnalysis
    analysis_stmt = select(PaperAnalysis).where(PaperAnalysis.paper_id.in_(request.paper_ids))
    analysis_result = await db.execute(analysis_stmt)
    analyses = {a.paper_id: a for a in analysis_result.scalars().all()}
    
    paper_dicts = [_paper_with_analysis_to_dict(p, analyses.get(p.id)) for p in papers]
    
    # Generate content using AI router
    content = await ai_router.compare(paper_dicts)
    
    # Create the comparison model
    comparison = Comparison(
        user_id=current_user.id,
        project_id=request.project_id if request.project_id else None,
        title=request.title,
        content=content.model_dump_json()
    )
    db.add(comparison)
    await db.commit()
    await db.refresh(comparison)
    
    # Add comparison papers
    for paper in papers:
        cp = ComparisonPaper(
            comparison_id=comparison.id,
            paper_id=paper.id
        )
        db.add(cp)
        
    await db.commit()
    
    return {
        "id": str(comparison.id),
        "title": comparison.title,
        "content": content.model_dump(),
        "project_id": str(comparison.project_id) if comparison.project_id else None,
        "paper_ids": [str(p.id) for p in papers],
        "created_at": comparison.created_at.isoformat()
    }

@router.get("/")
async def get_comparisons(
    project_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """List comparisons for the user, optionally filtered by project."""
    stmt = select(Comparison).options(
        selectinload(Comparison.comparison_papers).selectinload(ComparisonPaper.paper)
    ).where(Comparison.user_id == current_user.id)
    
    if project_id:
        stmt = stmt.where(Comparison.project_id == project_id)
        
    stmt = stmt.order_by(Comparison.created_at.desc())
    result = await db.execute(stmt)
    comparisons = result.scalars().all()
    
    res = []
    for c in comparisons:
        try:
            parsed_content = json.loads(c.content)
        except Exception:
            parsed_content = c.content
        res.append({
            "id": str(c.id),
            "title": c.title,
            "content": parsed_content,
            "project_id": str(c.project_id) if c.project_id else None,
            "paper_ids": [str(cp.paper_id) for cp in c.comparison_papers],
            "created_at": c.created_at.isoformat()
        })
    return res

@router.get("/{comparison_id}")
async def get_comparison(
    comparison_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Get a specific comparison."""
    stmt = select(Comparison).options(
        selectinload(Comparison.comparison_papers).selectinload(ComparisonPaper.paper)
    ).where(Comparison.id == comparison_id, Comparison.user_id == current_user.id)
    
    result = await db.execute(stmt)
    comparison = result.scalar_one_or_none()
    
    if not comparison:
        raise HTTPException(status_code=404, detail="Comparison not found")
        
    try:
        parsed_content = json.loads(comparison.content)
    except Exception:
        parsed_content = comparison.content
        
    return {
        "id": str(comparison.id),
        "title": comparison.title,
        "content": parsed_content,
        "project_id": str(comparison.project_id) if comparison.project_id else None,
        "paper_ids": [str(cp.paper_id) for cp in comparison.comparison_papers],
        "created_at": comparison.created_at.isoformat()
    }
