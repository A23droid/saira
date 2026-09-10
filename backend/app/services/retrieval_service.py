"""
Shared, scope-aware retrieval for every RAG surface in SAIRA.

This is the ONLY place that turns a question into evidence. Paper Chat and
Project Chat differ by exactly one thing — the `RetrievalScope` they pass in —
so there is no second copy of this logic to drift out of sync.

The scope is resolved to a concrete, explicit list of paper IDs **server-side**,
from the database, using the caller's user_id. The frontend never supplies the
retrieval scope; it supplies an identifier that this module verifies and expands.
That is what makes "Paper A cannot retrieve Paper B" an enforced invariant
rather than a UI convention.

Retrieval ranks knowledge entries with PostgreSQL full-text search, restricted
to the scoped papers (see `knowledge_retriever`). It deliberately applies the
scope before ranking: a global top-k followed by a filter can return fewer than
k in-scope results — or none — while in-scope entries that should have matched
are discarded. Scope is applied first, ranking second.

`RetrievedChunk` keeps its name and shape after the LLM-Wiki migration. What it
carries is now a knowledge entry rather than an embedded chunk, but every
consumer above this module — evidence formatting, citation validation, the chat
schemas, the frontend — reads the same fields, so the wire contract did not
move. `chunk_id` holds `KnowledgeEntry.entry_key`.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.paper import Paper
from app.models.project import Project
from app.models.project_paper import ProjectPaper

logger = logging.getLogger(__name__)

ScopeType = Literal["paper", "project"]


class ScopeError(Exception):
    """Raised when a scope cannot be resolved or is not owned by the caller."""

    def __init__(self, detail: str, status_code: int = 404) -> None:
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


# ── Scope ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RetrievalScope:
    """An explicit, verified retrieval boundary.

    `paper_ids` is always the authoritative list actually searched. For a paper
    scope it holds exactly one ID; for a project scope it holds every paper
    belonging to that project. Nothing outside this list can be retrieved.
    """

    type: ScopeType
    scope_id: str
    paper_ids: List[str]
    label: str = ""

    @property
    def is_empty(self) -> bool:
        return not self.paper_ids

    def to_log(self) -> Dict[str, Any]:
        return {
            "scope_type": self.type,
            "scope_id": self.scope_id,
            "paper_ids": list(self.paper_ids),
            "paper_count": len(self.paper_ids),
        }


@dataclass
class RetrievedChunk:
    """One piece of evidence, carrying everything a citation needs."""

    chunk_id: str
    paper_id: str
    page: Optional[int]
    chunk_index: Optional[int]
    text: str
    score: float
    paper_title: Optional[str] = None
    #: Detected section heading, new with the knowledge layer. Optional so a
    #: caller constructing one by hand (the evaluation harness does) is not
    #: forced to supply it.
    section: Optional[str] = None
    kind: str = "source"
    #: False only for compiled prose whose evidence quote could not be located
    #: in the paper's own text. `build_evidence_block` labels those.
    verified: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "paper_id": self.paper_id,
            "page": self.page,
            "chunk_index": self.chunk_index,
            "score": round(self.score, 6),
            "paper_title": self.paper_title,
            "section": self.section,
            "kind": self.kind,
            "verified": self.verified,
            "text_chars": len(self.text),
        }


@dataclass
class RetrievalResult:
    """Full, inspectable outcome of one retrieval — the evaluation harness and
    the debug logger both read this, so nothing about a run is hidden."""

    scope: RetrievalScope
    query: str
    chunks: List[RetrievedChunk] = field(default_factory=list)
    candidate_count: int = 0
    latency_ms: float = 0.0
    #: Retained so `RetrievalDebug` keeps its shape. Keyword retrieval has no
    #: embedding, so this is 0 — it is not a silently broken dimension.
    embedding_dim: int = 0
    error: Optional[str] = None

    @property
    def is_empty(self) -> bool:
        return not self.chunks

    def to_log(self) -> Dict[str, Any]:
        return {
            **self.scope.to_log(),
            "candidate_count": self.candidate_count,
            "retrieved_chunk_ids": [c.chunk_id for c in self.chunks],
            "retrieved_paper_ids": sorted({c.paper_id for c in self.chunks}),
            "retrieved_pages": [c.page for c in self.chunks],
            "similarity_scores": [round(c.score, 6) for c in self.chunks],
            "retrieval_latency_ms": round(self.latency_ms, 2),
            "embedding_dim": self.embedding_dim,
            "error": self.error,
        }


# ── Service ───────────────────────────────────────────────────────────────────

class RetrievalService:

    # -- Scope resolution (server-side, ownership-enforced) --------------------

    async def resolve_paper_scope(
        self,
        db: AsyncSession,
        paper_id: uuid.UUID | str,
        user_id: Optional[uuid.UUID] = None,
    ) -> RetrievalScope:
        """Resolve a single-paper scope.

        Papers are a shared catalogue rather than user-owned rows, so there is
        no ownership filter to apply here — but the paper must exist, so a
        caller can never search a scope that resolves to nothing silently.
        """
        pid = uuid.UUID(str(paper_id))
        paper = await db.scalar(select(Paper).where(Paper.id == pid))
        if paper is None:
            raise ScopeError("Paper not found.", status_code=404)
        return RetrievalScope(
            type="paper",
            scope_id=str(pid),
            paper_ids=[str(pid)],
            label=paper.title or "",
        )

    async def resolve_project_scope(
        self,
        db: AsyncSession,
        project_id: uuid.UUID | str,
        user_id: uuid.UUID,
    ) -> RetrievalScope:
        """Resolve a project scope to its member papers, enforcing ownership.

        `user_id` is required, not optional. An earlier version of the project
        context builder accepted `user_id=None` and skipped the ownership
        filter, which let a chat session pointed at someone else's project read
        that project's contents. Making the parameter mandatory removes the
        possibility of that call being written again.
        """
        prid = uuid.UUID(str(project_id))
        project = await db.scalar(select(Project).where(Project.id == prid))
        if project is None:
            raise ScopeError("Project not found.", status_code=404)
        if project.user_id != user_id:
            raise ScopeError("Access denied to this project.", status_code=403)

        rows = await db.execute(
            select(ProjectPaper.paper_id).where(ProjectPaper.project_id == prid)
        )
        paper_ids = [str(r[0]) for r in rows]
        return RetrievalScope(
            type="project",
            scope_id=str(prid),
            paper_ids=paper_ids,
            label=project.name or "",
        )

    async def resolve_scope(
        self,
        db: AsyncSession,
        scope_type: ScopeType,
        scope_id: uuid.UUID | str,
        user_id: uuid.UUID,
    ) -> RetrievalScope:
        if scope_type == "paper":
            return await self.resolve_paper_scope(db, scope_id, user_id)
        if scope_type == "project":
            return await self.resolve_project_scope(db, scope_id, user_id)
        raise ScopeError(f"Unknown scope type: {scope_type!r}", status_code=400)

    # -- Retrieval -------------------------------------------------------------

    async def retrieve(
        self,
        db: AsyncSession,
        scope: RetrievalScope,
        query: str,
        top_k: Optional[int] = None,
        kinds: Optional[Sequence[str]] = None,
    ) -> RetrievalResult:
        """Rank in-scope knowledge entries for this question.

        Never raises on retrieval failure: it returns an empty result carrying
        the error, so a degraded retrieval surfaces as "no evidence" (and the
        grounding policy makes the model abstain) instead of a 500.
        """
        from app.services.knowledge_retriever import knowledge_retriever

        if top_k is None:
            top_k = (
                settings.RAG_TOP_K_PAPER
                if scope.type == "paper"
                else settings.RAG_TOP_K_PROJECT
            )

        result = RetrievalResult(scope=scope, query=query)

        if scope.is_empty:
            result.error = "empty_scope"
            return result

        started = time.perf_counter()
        try:
            hits = await knowledge_retriever.search(
                db, query, scope.paper_ids, top_k=top_k, kinds=kinds
            )
            allowed = set(scope.paper_ids)
            for hit in hits:
                # Defence in depth, kept from the GraphRAG implementation: the
                # SQL already restricts to the scope, but an entry whose
                # paper_id falls outside it is dropped here rather than
                # reaching the model.
                if str(hit.paper_id) not in allowed:
                    logger.error(
                        "Scope violation dropped: entry %s (paper %s) not in scope %s",
                        hit.entry_key, hit.paper_id, scope.scope_id,
                    )
                    continue
                result.chunks.append(
                    RetrievedChunk(
                        chunk_id=hit.entry_key,
                        paper_id=str(hit.paper_id),
                        page=hit.page,
                        chunk_index=hit.ordinal,
                        text=hit.body or "",
                        score=float(hit.score or 0.0),
                        paper_title=hit.paper_title,
                        section=hit.section,
                        kind=hit.kind,
                        verified=hit.verified,
                    )
                )
            result.candidate_count = len(hits)
        except Exception as exc:  # noqa: BLE001 - degraded retrieval, not a crash
            logger.warning("Retrieval failed for scope %s: %s", scope.scope_id, exc)
            result.error = f"{type(exc).__name__}: {exc}"
        finally:
            result.latency_ms = (time.perf_counter() - started) * 1000.0

        return result

    # -- Evidence formatting ---------------------------------------------------

    def build_evidence_block(
        self,
        result: RetrievalResult,
        max_chunk_chars: Optional[int] = None,
        max_total_chars: Optional[int] = None,
    ) -> tuple[str, List[RetrievedChunk]]:
        """Render retrieved chunks as a labelled evidence block.

        Returns the block **and the chunks that actually fit**, because those
        are the only ones the model saw — and therefore the only ones a
        citation may legitimately refer to. Returning the truncated list is what
        lets the citation validator reject a reference to evidence that was
        dropped by the budget.
        """
        max_chunk_chars = max_chunk_chars or settings.RAG_MAX_CHUNK_CHARS
        max_total_chars = max_total_chars or settings.RAG_MAX_CONTEXT_CHARS

        lines: List[str] = []
        included: List[RetrievedChunk] = []
        used = 0

        for chunk in result.chunks:
            text = chunk.text[:max_chunk_chars]
            # `evidence_id=` stays the first token: the citation validator and
            # the evaluation harness both parse it positionally.
            section = f" | section={chunk.section}" if chunk.section else ""
            # Compiled prose whose quote could not be located is labelled in
            # the prompt itself, so the model can weigh it accordingly rather
            # than treating every block as equally attested.
            trust = "" if chunk.verified else " | UNVERIFIED"
            header = (
                f"[evidence_id={chunk.chunk_id} | paper_id={chunk.paper_id} "
                f"| page={chunk.page if chunk.page is not None else 'n/a'}"
                f"{section}{trust}]"
            )
            block = f"{header}\n{text}"
            if used + len(block) > max_total_chars and included:
                break
            lines.append(block)
            included.append(chunk)
            used += len(block)

        return "\n\n".join(lines), included


retrieval_service = RetrievalService()
