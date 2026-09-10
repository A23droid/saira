"""
Project AI endpoints.

All routes are scoped to a specific project and verify:
  1. current_user is authenticated
  2. project_id belongs to current_user (403 otherwise)
  3. All paper queries are constrained by the verified project_id

Routes:
    POST /projects/{project_id}/ai/chat             - Project-scoped chat with retrieval + citations
    POST /projects/{project_id}/ai/review/generate  - Trigger literature review pipeline
    GET  /projects/{project_id}/ai/review           - Fetch cached review
    DELETE /projects/{project_id}/ai/review         - Invalidate cached review
"""

import uuid
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.models.project import Project
from app.models.chat import ChatSession, ChatMessage
from app.schemas.ai import (
    ProjectChatRequest,
    ProjectChatResponse,
    LiteratureReviewResponse,
)
from app.services.ai_router import ai_router
from app.services.groq_service import GroqServiceError
from app.services.project_context import project_context_builder
from app.services.literature_review_service import literature_review_service
from app.services.retrieval_service import ScopeError, retrieval_service
from app.core.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)


# -- Authorization Helper -------------------------------------------------------

async def _get_verified_project(
    project_id: uuid.UUID,
    db: AsyncSession,
    current_user: User,
) -> Project:
    """
    Fetch a project and verify it belongs to current_user.
    Raises 404 if not found, 403 if not owned.
    """
    stmt = select(Project).where(Project.id == project_id)
    project = await db.scalar(stmt)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    if project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied to this project.")
    return project


def _handle_groq_error(exc: GroqServiceError) -> HTTPException:
    msg = str(exc)
    if "GROQ_API_KEY is not configured" in msg:
        return HTTPException(status_code=503, detail="AI features are not configured. Set GROQ_API_KEY.")
    if "rate limit" in msg.lower():
        return HTTPException(status_code=429, detail="AI rate limit reached. Please wait and try again.")
    if "timed out" in msg.lower():
        return HTTPException(status_code=504, detail="AI request timed out. Please try again.")
    logger.error("Groq error in project AI: %s", msg)
    return HTTPException(status_code=502, detail=f"AI service error: {msg}")


# -- Project Chat ---------------------------------------------------------------

@router.post("/{project_id}/ai/chat", response_model=ProjectChatResponse)
async def project_chat(
    project_id: uuid.UUID,
    req: ProjectChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProjectChatResponse:
    """
    Answer a question about papers in a specific project.

    Architecture:
      1. Verify project ownership
      2. Knowledge retrieval: rank in-scope knowledge entries (Postgres FTS)
      3. Build a bounded evidence block from the entries that fit
      4. Call the configured LLM with that evidence + conversation history
      5. Parse and validate citations (only papers from this project)
      6. Persist message to chat session (create session if needed)
      7. Return grounded answer with citations
    """
    project = await _get_verified_project(project_id, db, current_user)

    if not req.message or not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    # -- Resolve scope server-side --------------------------------------------
    # The scope is derived from the verified project, never from the request
    # body, and it expands to the project's papers inside the retrieval layer.
    try:
        scope = await retrieval_service.resolve_project_scope(db, project_id, current_user.id)
    except ScopeError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)

    if scope.is_empty:
        return ProjectChatResponse(
            answer="This project has no papers yet. Add papers to the project before asking questions.",
            citations=[], grounded=False, model=None,
        )

    # -- Load bounded conversation history -------------------------------------
    history = []
    active_session_id = req.session_id
    if active_session_id and not settings.eval_mode:
        try:
            session_uuid = uuid.UUID(active_session_id)
            stmt = (
                select(ChatSession)
                .options(selectinload(ChatSession.messages))
                .where(
                    ChatSession.id == session_uuid,
                    ChatSession.user_id == current_user.id,
                    ChatSession.project_id == project_id,
                )
            )
            chat_session = await db.scalar(stmt)
            if chat_session:
                recent = chat_session.messages[-settings.RAG_MAX_HISTORY_MESSAGES:]
                history = [{"role": m.role, "content": m.content} for m in recent]
            else:
                active_session_id = None
        except (ValueError, Exception) as exc:
            logger.warning("Could not load chat session %s: %s", active_session_id, exc)
            active_session_id = None

    # -- Retrieve, then generate ----------------------------------------------
    retrieval = await retrieval_service.retrieve(db, scope, req.message)
    try:
        scoped = await ai_router.answer_scoped(
            scope=scope, question=req.message, retrieval=retrieval, history=history,
        )
    except GroqServiceError as exc:
        raise _handle_groq_error(exc)

    ai_resp = ProjectChatResponse(
        answer=scoped.answer,
        citations=scoped.citations,
        grounded=scoped.grounded,
        model=scoped.model,
    )

    # -- Persist to chat session ------------------------------------------------
    try:
        if not active_session_id:
            chat_session = ChatSession(
                user_id=current_user.id,
                project_id=project_id,
                paper_id=None,
                title=req.message[:60] + ("..." if len(req.message) > 60 else ""),
            )
            db.add(chat_session)
            await db.flush()
            active_session_id = str(chat_session.id)
        else:
            chat_session = await db.scalar(
                select(ChatSession).where(ChatSession.id == uuid.UUID(active_session_id))
            )

        db.add(ChatMessage(
            session_id=chat_session.id, role="user",
            content=req.message, cited_paper_ids=[],
        ))
        db.add(ChatMessage(
            session_id=chat_session.id, role="assistant",
            content=scoped.answer,
            cited_paper_ids=sorted({c.paper_id for c in scoped.citations}),
        ))
        await db.commit()
    except Exception as exc:
        logger.error("Failed to persist chat messages: %s", exc)
        await db.rollback()

    # Attach session ID to response
    ai_resp.session_id = active_session_id
    return ai_resp


# -- Literature Review ----------------------------------------------------------

@router.post("/{project_id}/ai/review/generate", response_model=LiteratureReviewResponse)
async def generate_literature_review(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LiteratureReviewResponse:
    """
    Generate a literature review for a project.

    This is a multi-stage pipeline:
      Stage 1: Fetch all project papers (user-authorized)
      Stage 2: Compute paper-set fingerprint
      Stage 3: Cache check (return if unchanged paper set)
      Stage 4: Per-paper analysis via GPT-OSS 120B (batched)
      Stage 5: Cross-paper synthesis via GPT-OSS 120B
      Stage 6: Persist to literature_reviews
      Stage 7: Return structured response

    For large projects, paper analysis is batched (10 papers/batch).
    """
    # Verify ownership
    await _get_verified_project(project_id, db, current_user)

    try:
        return await literature_review_service.generate(
            session=db,
            project_id=project_id,
            user_id=current_user.id,
            force_regenerate=False,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except GroqServiceError as exc:
        raise _handle_groq_error(exc)


@router.post("/{project_id}/ai/review/regenerate", response_model=LiteratureReviewResponse)
async def regenerate_literature_review(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LiteratureReviewResponse:
    """Force-regenerate the literature review, bypassing the cache."""
    await _get_verified_project(project_id, db, current_user)

    try:
        return await literature_review_service.generate(
            session=db,
            project_id=project_id,
            user_id=current_user.id,
            force_regenerate=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except GroqServiceError as exc:
        raise _handle_groq_error(exc)


@router.get("/{project_id}/ai/review", response_model=LiteratureReviewResponse)
async def get_literature_review(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LiteratureReviewResponse:
    """
    Fetch the cached literature review for a project.
    Returns 404 if no review has been generated yet.
    The is_stale flag indicates whether the paper set has changed since generation.
    """
    await _get_verified_project(project_id, db, current_user)

    # Get current paper IDs to check staleness
    _, paper_dicts = await project_context_builder.get_all_paper_dicts(
        session=db,
        project_id=project_id,
        user_id=current_user.id,
    )
    current_paper_ids = [p["id"] for p in paper_dicts]

    cached = await literature_review_service.get_cached_review(
        session=db,
        project_id=project_id,
        user_id=current_user.id,
        current_paper_ids=current_paper_ids,
    )
    if not cached:
        raise HTTPException(status_code=404, detail="No literature review has been generated for this project yet.")

    return cached


@router.delete("/{project_id}/ai/review", status_code=204)
async def delete_literature_review(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Invalidate (delete) the cached literature review for a project."""
    await _get_verified_project(project_id, db, current_user)

    deleted = await literature_review_service.invalidate(
        session=db,
        project_id=project_id,
        user_id=current_user.id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="No literature review found to delete.")
