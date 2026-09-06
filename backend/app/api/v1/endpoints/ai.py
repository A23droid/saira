"""
AI API endpoints for SAIRA.

All routes follow the existing project conventions:
- Auth via get_current_user dependency
- DB access via get_db dependency
- Errors surfaced as HTTPException (never raw stack traces)

Route structure:
    GET  /ai/status          — Check if Groq is configured
    POST /ai/summary         — Llama 3.3 70B: structured summary
    POST /ai/extract         — GPT-OSS 120B: structured extraction
    POST /ai/qa              — Llama 3.3 70B: Q&A
"""

import uuid
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.schemas.ai import (
    AISummaryRequest,
    AIExtractionRequest,
    AIQARequest,
    PRDRequest,
    IndependentReviewRequest,
    AISummaryResponse,
    AIExtractionResponse,
    AIQAResponse,
    PRDResponse,
    AIStatusResponse,
    LiteratureReviewContent
)
from app.services.ai_router import ai_router
from app.services.prd_engine import prd_engine
from app.services.groq_service import GroqServiceError
from app.services.paper_service import paper_service
from app.core.config import settings
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()
logger = logging.getLogger(__name__)


def _paper_to_dict(paper: Any) -> dict:
    """Convert a Paper ORM model to a plain dict for the AI layer."""
    return {
        "id": str(paper.id),
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


def _handle_groq_error(exc: GroqServiceError) -> HTTPException:
    """Map GroqServiceError to an appropriate HTTP response."""
    msg = str(exc)
    if "GROQ_API_KEY is not configured" in msg:
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI features are not configured on this server. Set GROQ_API_KEY in .env.",
        )
    if "rate limit" in msg.lower():
        return HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="AI rate limit reached. Please try again in a moment.",
        )
    if "Invalid GROQ_API_KEY" in msg:
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service configuration error. Contact the administrator.",
        )
    if "timed out" in msg.lower():
        return HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="AI request timed out. Please try again.",
        )
    logger.error("Groq error surfaced to API: %s", msg)
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"AI service error: {msg}",
    )


# ── Status ─────────────────────────────────────────────────────────────────────

@router.get("/status", response_model=AIStatusResponse)
async def ai_status(
    current_user: User = Depends(get_current_user),
) -> AIStatusResponse:
    """Check whether Groq AI is configured and which models are active."""
    configured = bool(settings.GROQ_API_KEY)
    return AIStatusResponse(
        configured=configured,
        primary_model=settings.GROQ_PRIMARY_MODEL,
        extraction_model=settings.GROQ_EXTRACTION_MODEL,
        message="AI features ready." if configured else "GROQ_API_KEY not set.",
    )


# ── Summary (Llama 3.3 70B) ────────────────────────────────────────────────────

@router.post("/summary", response_model=AISummaryResponse)
async def get_paper_summary(
    req: AISummaryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AISummaryResponse:
    """
    Generate a structured AI summary of a paper using Llama 3.3 70B.
    Context is built from the paper's stored metadata — no PDF required.
    """
    try:
        paper_id = uuid.UUID(req.paper_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid paper ID format.")

    paper = await paper_service.get_paper_by_id(session=db, paper_id=paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found.")

    try:
        return await ai_router.summarize(_paper_to_dict(paper))
    except GroqServiceError as exc:
        raise _handle_groq_error(exc)


# ── Extraction (GPT-OSS 120B) ──────────────────────────────────────────────────

@router.post("/extract", response_model=AIExtractionResponse)
async def extract_paper_info(
    req: AIExtractionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AIExtractionResponse:
    """
    Extract structured research information from a paper using GPT-OSS 120B.
    Returns datasets, models, algorithms, metrics, limitations, and future work.
    """
    try:
        paper_id = uuid.UUID(req.paper_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid paper ID format.")

    paper = await paper_service.get_paper_by_id(session=db, paper_id=paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found.")

    if not paper.pdf_url:
        raise HTTPException(
            status_code=400,
            detail="PDF unavailable: Cannot perform deep analysis without the full text document."
        )

    try:
        return await ai_router.extract(_paper_to_dict(paper))
    except GroqServiceError as exc:
        raise _handle_groq_error(exc)


# ── Q&A (Llama 3.3 70B) ───────────────────────────────────────────────────────

@router.post("/qa", response_model=AIQAResponse)
async def paper_qa(
    req: AIQARequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AIQAResponse:
    """
    Answer a question about a paper using Llama 3.3 70B.
    Responses are grounded in the paper's stored metadata.
    """
    try:
        paper_id = uuid.UUID(req.paper_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid paper ID format.")

    if not req.question or not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    paper = await paper_service.get_paper_by_id(session=db, paper_id=paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found.")

    if not paper.pdf_url:
        raise HTTPException(
            status_code=400,
            detail="PDF unavailable: Cannot perform deep analysis without the full text document."
        )

    try:
        return await ai_router.answer_question(_paper_to_dict(paper), req.question)
    except GroqServiceError as exc:
        raise _handle_groq_error(exc)


# ── Personalized Research Delta (PRD) ─────────────────────────────────────────

@router.post("/prd", response_model=PRDResponse)
async def calculate_prd(
    req: PRDRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PRDResponse:
    """
    Calculate the Personalized Research Delta (PRD) for a candidate paper 
    against a user's specific project workspace.
    """
    try:
        paper_id = uuid.UUID(req.paper_id)
        project_id = uuid.UUID(req.project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format.")

    paper = await paper_service.get_paper_by_id(session=db, paper_id=paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Candidate paper not found.")

    try:
        return await prd_engine.calculate_prd(session=db, project_id=project_id, paper=paper)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except GroqServiceError as exc:
        raise _handle_groq_error(exc)


# ── Independent Literature Review ─────────────────────────────────────────────

@router.post("/review", response_model=LiteratureReviewContent)
async def generate_independent_review(
    req: IndependentReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LiteratureReviewContent:
    """
    Generate an independent literature review for an arbitrary list of papers.
    """
    import asyncio
    
    if not req.paper_ids:
        raise HTTPException(status_code=400, detail="Must provide at least one paper ID.")
    
    if len(req.paper_ids) > 20:
        raise HTTPException(status_code=400, detail="Maximum 20 papers allowed for independent review.")
        
    paper_dicts = []
    for pid in req.paper_ids:
        try:
            puuid = uuid.UUID(pid)
            p = await paper_service.get_paper_by_id(session=db, paper_id=puuid)
            if p:
                paper_dicts.append(_paper_to_dict(p))
        except ValueError:
            continue
            
    if not paper_dicts:
        raise HTTPException(status_code=404, detail="No valid papers found.")
        
    # Analyze papers in parallel (or batched)
    BATCH_SIZE = 10
    analyses = []
    for i in range(0, len(paper_dicts), BATCH_SIZE):
        batch = paper_dicts[i: i + BATCH_SIZE]
        tasks = [ai_router.analyze_paper_for_review(p) for p in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for j, result in enumerate(results):
            if isinstance(result, Exception):
                analyses.append({
                    "paper_id": str(batch[j].get("id", "")),
                    "title": batch[j].get("title", "Unknown"),
                    "year": batch[j].get("publication_year"),
                    "authors": "Unknown",
                    "research_problem": None, "methodology": None,
                    "datasets": [], "models": [], "algorithms": [],
                    "metrics": [], "key_findings": [], "limitations": [],
                    "future_work": [], "contribution": None,
                })
            else:
                analyses.append(result)
                
    try:
        content = await ai_router.synthesize_literature_review(analyses, "Independent Custom Review")
        return content
    except GroqServiceError as exc:
        raise _handle_groq_error(exc)
