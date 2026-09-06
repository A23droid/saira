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

Retrieval is a similarity scan restricted to the scoped chunks (see
`neo4j_service.search_chunks`). It deliberately does not query the global vector
index and filter afterwards: a global top-k followed by a filter can return
fewer than k in-scope results — or none — while in-scope chunks that should have
matched are discarded. Scope is applied first, ranking second.
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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "paper_id": self.paper_id,
            "page": self.page,
            "chunk_index": self.chunk_index,
            "score": round(self.score, 6),
            "paper_title": self.paper_title,
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
        scope: RetrievalScope,
        query: str,
        top_k: Optional[int] = None,
        neo_session: Any = None,
    ) -> RetrievalResult:
        """Embed the query and return the top-k in-scope chunks.

        Never raises on retrieval failure: it returns an empty result carrying
        the error, so a degraded retrieval surfaces as "no evidence" (and the
        grounding policy makes the model abstain) instead of a 500.
        """
        from app.db.neo4j_client import neo4j_client
        from app.services.embedding_service import embedding_service
        from app.services.neo4j_service import neo4j_service
        import asyncio

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
            # Embedding is CPU-bound; keep it off the event loop. The endpoint
            # layer used to call this synchronously, stalling every other
            # in-flight request for the duration of the encode.
            embedding = await asyncio.to_thread(embedding_service.embed_text, query)
            result.embedding_dim = len(embedding)

            owns_session = neo_session is None
            if owns_session:
                neo_session = await neo4j_client.get_session()
                async with neo_session:
                    rows = await neo4j_service.search_chunks(
                        neo_session, scope.paper_ids, embedding, top_k=top_k
                    )
            else:
                rows = await neo4j_service.search_chunks(
                    neo_session, scope.paper_ids, embedding, top_k=top_k
                )

            allowed = set(scope.paper_ids)
            for row in rows:
                # Defence in depth: the Cypher already restricts to the scope,
                # but a chunk whose paper_id somehow falls outside it is dropped
                # here rather than reaching the model.
                if str(row.get("paper_id")) not in allowed:
                    logger.error(
                        "Scope violation dropped: chunk %s (paper %s) not in scope %s",
                        row.get("id"), row.get("paper_id"), scope.scope_id,
                    )
                    continue
                result.chunks.append(
                    RetrievedChunk(
                        chunk_id=row.get("id"),
                        paper_id=str(row.get("paper_id")),
                        page=row.get("page"),
                        chunk_index=row.get("chunk_index"),
                        text=row.get("text") or "",
                        score=float(row.get("score") or 0.0),
                        paper_title=row.get("paper_title"),
                    )
                )
            result.candidate_count = len(rows)
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
            header = (
                f"[evidence_id={chunk.chunk_id} | paper_id={chunk.paper_id} "
                f"| page={chunk.page if chunk.page is not None else 'n/a'}]"
            )
            block = f"{header}\n{text}"
            if used + len(block) > max_total_chars and included:
                break
            lines.append(block)
            included.append(chunk)
            used += len(block)

        return "\n\n".join(lines), included


retrieval_service = RetrievalService()
