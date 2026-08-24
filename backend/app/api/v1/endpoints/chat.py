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
from app.schemas.ai import AIQARequest, AIQAResponse
from app.services.ai_router import ai_router
from app.services.project_context import project_context_builder
from app.api.v1.endpoints.ai import _paper_to_dict

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
    """Create a new chat session."""
    session = ChatSession(
        user_id=current_user.id,
        project_id=data.get("project_id"),
        paper_id=data.get("paper_id"),
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

    # Add user message
    user_msg = ChatMessage(
        session_id=session.id,
        role="user",
        content=request.question,
        cited_paper_ids=[]
    )
    db.add(user_msg)
    
    # Build history for context
    history = [{"role": m.role, "content": m.content} for m in session.messages]

    # Generate AI response based on context
    ai_resp = None
    if session.paper_id:
        paper = await db.scalar(select(Paper).where(Paper.id == session.paper_id))
        if not paper:
            raise HTTPException(status_code=404, detail="Context paper not found")
        ai_resp = await ai_router.answer_question(_paper_to_dict(paper), request.question, history)
    elif session.project_id:
        proj_context = await project_context_builder.build_context(db, session.project_id)
        ai_resp = await ai_router.project_answer_question(proj_context, request.question, history)
    else:
        raise HTTPException(status_code=400, detail="Session has no context (no paper or project)")

    # Add AI message
    ai_msg = ChatMessage(
        session_id=session.id,
        role="assistant",
        content=ai_resp.answer,
        cited_paper_ids=[] # You'd extract these if parsed from the answer
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
            "model": ai_resp.model
        }
    }
