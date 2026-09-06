import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.models.chat import ChatSession, ChatMessage
from app.models.paper import Paper
from app.core.config import settings
from app.schemas.ai import AIQARequest
from app.services.ai_router import ai_router
from app.services.groq_service import GroqServiceError
from app.services.retrieval_service import ScopeError, retrieval_service

router = APIRouter()


@router.get("/sessions")
async def get_chat_sessions(
    project_id: uuid.UUID | None = None,
    paper_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Get all chat sessions for the current user, optionally filtered by project or paper."""
    stmt = select(ChatSession).where(ChatSession.user_id == current_user.id)
    if project_id:
        stmt = stmt.where(ChatSession.project_id == project_id)
    if paper_id:
        stmt = stmt.where(ChatSession.paper_id == paper_id)
        
    stmt = stmt.order_by(ChatSession.updated_at.desc())
    result = await db.execute(stmt)
    sessions = result.scalars().all()
    
    return [
        {
            "id": str(s.id),
            "project_id": str(s.project_id) if s.project_id else None,
            "paper_id": str(s.paper_id) if s.paper_id else None,
            "title": s.title,
            "created_at": s.created_at.isoformat(),
            "updated_at": s.updated_at.isoformat()
        } for s in sessions
    ]


@router.post("/sessions")
async def create_chat_session(
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Create a new chat session.

    The project/paper context is verified here, at creation time. Previously
    this accepted whatever `project_id` the client sent with no ownership
    check; combined with the project context builder being called without a
    `user_id` further down, that let a session be pointed at another user's
    project and read its contents back through the answer. Both halves are now
    closed — this endpoint rejects a foreign project, and retrieval scope
    resolution requires a user_id.
    """
    project_id = data.get("project_id")
    paper_id = data.get("paper_id")

    if project_id:
        try:
            scope = await retrieval_service.resolve_project_scope(
                db, project_id, current_user.id
            )
        except ScopeError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail)
        project_id = scope.scope_id

    if paper_id:
        try:
            paper_scope = await retrieval_service.resolve_paper_scope(db, paper_id)
        except ScopeError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail)
        paper_id = paper_scope.scope_id

    if not project_id and not paper_id:
        raise HTTPException(
            status_code=400,
            detail="A chat session requires either a project_id or a paper_id.",
        )

    session = ChatSession(
        user_id=current_user.id,
        project_id=project_id,
        paper_id=paper_id,
        title=data.get("title", "New Chat")
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return {
        "id": str(session.id),
        "title": session.title,
        "project_id": str(session.project_id) if session.project_id else None,
        "paper_id": str(session.paper_id) if session.paper_id else None,
        "created_at": session.created_at.isoformat()
    }


@router.get("/sessions/{session_id}")
async def get_chat_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Get a chat session with its messages."""
    stmt = select(ChatSession).options(selectinload(ChatSession.messages)).where(
        ChatSession.id == session_id, ChatSession.user_id == current_user.id
    )
    session = await db.scalar(stmt)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    return {
        "id": str(session.id),
        "title": session.title,
        "project_id": str(session.project_id) if session.project_id else None,
        "paper_id": str(session.paper_id) if session.paper_id else None,
        "messages": [
            {
                "id": str(m.id),
                "role": m.role,
                "content": m.content,
                "cited_paper_ids": m.cited_paper_ids,
                "created_at": m.created_at.isoformat()
            } for m in session.messages
        ]
    }


@router.post("/sessions/{session_id}/messages")
async def add_chat_message(
    session_id: uuid.UUID,
    request: AIQARequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Add a message to a session and get AI response."""
    # Ensure session exists and belongs to user
    stmt = select(ChatSession).options(selectinload(ChatSession.messages)).where(
        ChatSession.id == session_id, ChatSession.user_id == current_user.id
    )
    session = await db.scalar(stmt)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if not request.question or not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    # Add user message
    user_msg = ChatMessage(
        session_id=session.id,
        role="user",
        content=request.question,
        cited_paper_ids=[]
    )
    db.add(user_msg)

    # Bounded history. This used to pass every message the session had ever
    # accumulated, which grew the prompt without limit and (with a reasoning
    # model billing its chain of thought against max_tokens) eventually
    # returned empty answers. In evaluation mode no history is sent at all, so
    # a previous turn cannot supply a fact the current retrieval did not.
    if settings.eval_mode:
        history = []
    else:
        recent = session.messages[-settings.RAG_MAX_HISTORY_MESSAGES:]
        history = [{"role": m.role, "content": m.content} for m in recent]

    # -- Resolve scope server-side ---------------------------------------------
    try:
        if session.paper_id:
            scope = await retrieval_service.resolve_paper_scope(db, session.paper_id)
        elif session.project_id:
            scope = await retrieval_service.resolve_project_scope(
                db, session.project_id, current_user.id
            )
        else:
            raise HTTPException(
                status_code=400, detail="Session has no context (no paper or project)"
            )
    except ScopeError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)

    if scope.is_empty:
        raise HTTPException(
            status_code=400,
            detail="This project has no papers yet. Add papers before asking questions.",
        )

    # -- Retrieve, then generate ----------------------------------------------
    retrieval = await retrieval_service.retrieve(scope, request.question)
    try:
        ai_resp = await ai_router.answer_scoped(
            scope=scope, question=request.question,
            retrieval=retrieval, history=history,
        )
    except GroqServiceError as exc:
        raise HTTPException(status_code=502, detail=f"AI service error: {exc}")

    # Citations are already validated against the evidence actually sent to the
    # model, so these IDs cannot reference a paper outside the scope.
    cited_paper_ids = sorted({c.paper_id for c in ai_resp.citations})

    ai_msg = ChatMessage(
        session_id=session.id,
        role="assistant",
        content=ai_resp.answer,
        cited_paper_ids=cited_paper_ids,
    )
    db.add(ai_msg)

    await db.commit()
    await db.refresh(ai_msg)

    return {
        "user_message": {
            "id": str(user_msg.id),
            "role": user_msg.role,
            "content": user_msg.content,
        },
        "ai_message": {
            "id": str(ai_msg.id),
            "role": ai_msg.role,
            "content": ai_msg.content,
            "grounded": ai_resp.grounded,
            "abstained": ai_resp.abstained,
            "model": ai_resp.model,
            "cited_paper_ids": cited_paper_ids,
            "citations": [c.model_dump() for c in ai_resp.citations],
            "evidence": [e.model_dump() for e in ai_resp.evidence],
            "retrieval": ai_resp.retrieval.model_dump() if ai_resp.retrieval else None,
        }
    }
