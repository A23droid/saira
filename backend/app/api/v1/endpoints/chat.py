import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.models.chat import ChatSession, ChatMessage
from app.models.paper import Paper
from app.models.project import Project
from app.models.project_paper import ProjectPaper
from app.core.config import settings
from app.schemas.ai import AIQARequest
from app.services.ai_router import ai_router
from app.services.groq_service import GroqServiceError
from app.services.retrieval_service import ScopeError, retrieval_service

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Paper chat persistence ────────────────────────────────────────────────────
#
# A paper chat is persistent if — and only if — the paper is saved in one of the
# caller's projects. Persistence is derived from that association rather than
# stored as a flag, so it cannot drift out of step with it: opening a paper,
# indexing it, or asking a question never makes a chat persistent, and removing
# the paper from every project makes future chats ephemeral again.
#
# Identity is (user, paper), matching what the product already does — the
# existing panel looks a session up by `paper_id` alone and `project_id` is left
# NULL on paper sessions. A paper saved in two projects keeps one conversation.
# Making chat project-scoped would be a new sharing behaviour, not a smaller
# one, so it is deliberately not introduced here.

_MAX_TURN_CHARS = 8000


class ChatTurn(BaseModel):
    """One client-held ephemeral message.

    Ephemeral history lives in the browser, so it re-enters the server as
    untrusted input and is bounded here. It only ever shapes the caller's own
    prompt — it is never stored and never widens retrieval scope.
    """

    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=_MAX_TURN_CHARS)


class EphemeralAskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=_MAX_TURN_CHARS)
    history: List[ChatTurn] = Field(default_factory=list)


class PromoteRequest(BaseModel):
    messages: List[ChatTurn] = Field(default_factory=list)


async def _is_paper_saved(
    db: AsyncSession, paper_id: uuid.UUID | str, user_id: uuid.UUID
) -> bool:
    """True when the paper sits in a project owned by this user."""
    stmt = (
        select(ProjectPaper.id)
        .join(Project, Project.id == ProjectPaper.project_id)
        .where(ProjectPaper.paper_id == paper_id, Project.user_id == user_id)
        .limit(1)
    )
    return await db.scalar(stmt) is not None


async def _persistent_session(
    db: AsyncSession,
    paper_id: uuid.UUID | str,
    user_id: uuid.UUID,
    create: bool = False,
) -> ChatSession | None:
    """Get — or optionally create — the one persistent session for this pair.

    Always the oldest match, so a duplicate created by two simultaneous opens is
    inert rather than a second visible conversation.

    ponytail: no unique constraint on (user_id, paper_id); ordering makes a race
    harmless without a migration. Add the constraint if duplicates ever matter.
    """
    stmt = (
        select(ChatSession)
        .options(selectinload(ChatSession.messages))
        .where(
            ChatSession.user_id == user_id,
            ChatSession.paper_id == paper_id,
            ChatSession.project_id.is_(None),
        )
        .order_by(ChatSession.created_at.asc())
        .limit(1)
    )
    session = await db.scalar(stmt)
    if session or not create:
        return session

    session = ChatSession(user_id=user_id, paper_id=paper_id, title="Paper Chat")
    db.add(session)
    await db.commit()
    await db.refresh(session)
    logger.info(
        "paper_chat_session_created paper_id=%s user_id=%s session_id=%s",
        paper_id, user_id, session.id,
    )
    # Re-read through the eager-loading query. A just-created instance has no
    # `messages` collection loaded, and touching it would lazy-load outside the
    # async context.
    return await db.scalar(stmt)


def _ordered_now(count: int) -> list[datetime]:
    """Distinct, increasing timestamps for rows written in one transaction.

    Postgres `now()` is the transaction timestamp, so every row committed
    together shares it — and `ChatSession.messages` orders by `created_at`. A
    user/assistant pair, or a migrated conversation, would come back in an
    arbitrary order without this.
    """
    base = datetime.now(timezone.utc)
    return [base + timedelta(microseconds=i) for i in range(count)]


async def _answer_in_scope(scope, question: str, history: list[dict]):
    """Retrieve, then generate. Shared by the persistent and ephemeral paths so
    they cannot drift apart on scoping or citation validation."""
    retrieval = await retrieval_service.retrieve(scope, question)
    try:
        return await ai_router.answer_scoped(
            scope=scope, question=question, retrieval=retrieval, history=history,
        )
    except GroqServiceError as exc:
        raise HTTPException(status_code=502, detail=f"AI service error: {exc}")


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

        # Persistence is earned by saving the paper, and this is where that is
        # enforced — a client cannot get permanent history for an unsaved paper
        # by calling the session endpoint directly instead of the ephemeral one.
        if not project_id and not await _is_paper_saved(db, paper_id, current_user.id):
            raise HTTPException(
                status_code=409,
                detail=(
                    "This paper is not saved to any of your projects. "
                    "Use the ephemeral paper chat, or add the paper to a project first."
                ),
            )

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

    # Add user message. Both rows commit together, so their timestamps are set
    # explicitly — see _ordered_now — or the restored history comes back with
    # the answer possibly ahead of its question.
    asked_at, answered_at = _ordered_now(2)
    user_msg = ChatMessage(
        session_id=session.id,
        role="user",
        content=request.question,
        cited_paper_ids=[],
        created_at=asked_at,
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
    ai_resp = await _answer_in_scope(scope, request.question, history)

    # Citations are already validated against the evidence actually sent to the
    # model, so these IDs cannot reference a paper outside the scope.
    cited_paper_ids = sorted({c.paper_id for c in ai_resp.citations})

    ai_msg = ChatMessage(
        session_id=session.id,
        role="assistant",
        content=ai_resp.answer,
        cited_paper_ids=cited_paper_ids,
        created_at=answered_at,
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


# ── Paper chat: ephemeral vs persistent ───────────────────────────────────────


@router.get("/papers/{paper_id}/context")
async def get_paper_chat_context(
    paper_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Which mode this paper's Ask AI runs in, plus any history to restore.

    The panel calls this on open. In persistent mode the session is created here
    if it does not exist yet, so reopening a saved paper always lands on the same
    conversation instead of starting a new one.
    """
    try:
        await retrieval_service.resolve_paper_scope(db, paper_id)
    except ScopeError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)

    if not await _is_paper_saved(db, paper_id, current_user.id):
        # Ephemeral papers still need chunks to answer from, and the canonical
        # pipeline is the only thing that makes them. It is deduplicated, so a
        # paper already indexed by search ingest is untouched.
        from app.services.indexing_jobs import ensure_indexed

        await ensure_indexed(paper_id)
        logger.info(
            "paper_chat_opened mode=ephemeral paper_id=%s user_id=%s",
            paper_id, current_user.id,
        )
        return {"mode": "ephemeral", "session_id": None, "messages": []}

    session = await _persistent_session(db, paper_id, current_user.id, create=True)
    logger.info(
        "paper_chat_opened mode=persistent paper_id=%s user_id=%s session_id=%s messages=%d",
        paper_id, current_user.id, session.id, len(session.messages),
    )
    return {
        "mode": "persistent",
        "session_id": str(session.id),
        "messages": [
            {
                "id": str(m.id),
                "role": m.role,
                "content": m.content,
                "cited_paper_ids": m.cited_paper_ids,
                "created_at": m.created_at.isoformat(),
            }
            for m in session.messages
        ],
    }


@router.post("/papers/{paper_id}/ephemeral")
async def ask_paper_ephemeral(
    paper_id: uuid.UUID,
    request: EphemeralAskRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Answer a question about an unsaved paper without storing anything.

    No ChatSession, no ChatMessage, no project association — the conversation
    exists only in the caller's page. Retrieval is still resolved server-side and
    still scoped to this one paper.
    """
    if await _is_paper_saved(db, paper_id, current_user.id):
        raise HTTPException(
            status_code=409,
            detail="This paper is saved to a project; use its persistent chat session.",
        )

    try:
        scope = await retrieval_service.resolve_paper_scope(db, paper_id)
    except ScopeError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)

    history = [
        {"role": t.role, "content": t.content}
        for t in request.history[-settings.RAG_MAX_HISTORY_MESSAGES:]
    ]
    if settings.eval_mode:
        history = []

    ai_resp = await _answer_in_scope(scope, request.question, history)
    return {
        "ai_message": {
            "role": "assistant",
            "content": ai_resp.answer,
            "grounded": ai_resp.grounded,
            "abstained": ai_resp.abstained,
            "model": ai_resp.model,
            "cited_paper_ids": sorted({c.paper_id for c in ai_resp.citations}),
            "citations": [c.model_dump() for c in ai_resp.citations],
            "evidence": [e.model_dump() for e in ai_resp.evidence],
            "retrieval": ai_resp.retrieval.model_dump() if ai_resp.retrieval else None,
        }
    }


@router.post("/papers/{paper_id}/promote")
async def promote_paper_chat(
    paper_id: uuid.UUID,
    request: PromoteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Carry an ephemeral conversation into the persistent session after a save.

    Only valid once the paper really is saved, which is what makes this safe to
    expose: it cannot be used to manufacture history for a paper the user never
    kept. Migration runs only into an empty session, so calling it twice — a
    retry, a double click — cannot duplicate the conversation.
    """
    if not await _is_paper_saved(db, paper_id, current_user.id):
        raise HTTPException(
            status_code=409,
            detail="Paper is not saved to any of your projects; nothing to promote into.",
        )

    session = await _persistent_session(db, paper_id, current_user.id, create=True)

    migrated = 0
    if request.messages and not session.messages:
        stamps = _ordered_now(len(request.messages))
        for turn, created_at in zip(request.messages, stamps):
            db.add(ChatMessage(
                session_id=session.id,
                role=turn.role,
                content=turn.content,
                # Citations belong to the evidence of a specific retrieval and
                # are not replayed: the migrated text keeps the conversation,
                # not stale provenance.
                cited_paper_ids=[],
                created_at=created_at,
            ))
        migrated = len(request.messages)
        await db.commit()

    logger.info(
        "paper_chat_promoted paper_id=%s user_id=%s session_id=%s migrated=%d",
        paper_id, current_user.id, session.id, migrated,
    )
    return {
        "mode": "persistent",
        "session_id": str(session.id),
        "migrated": migrated,
    }
