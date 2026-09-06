"""
Dynamic evaluation-corpus discovery.

No paper is hardcoded as the evaluation target. Candidates are discovered at
run time through SAIRA's own arXiv client, so the harness exercises whatever
the live pipeline can actually find and ingest. If discovery or ingestion
fails, that is reported as a finding rather than papered over with a fallback
to a known-good document.

A previously-ingested document may be reused when `allow_existing=True`, which
keeps repeat runs cheap; the selection is still made by query at run time, not
by a constant ID in the source.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class EvalDocument:
    paper_id: str
    title: str
    arxiv_id: Optional[str]
    pdf_url: Optional[str]
    chunk_count: int = 0
    source: str = "discovered"      # discovered | reused

    def to_dict(self) -> Dict[str, Any]:
        return {
            "paper_id": self.paper_id, "title": self.title,
            "arxiv_id": self.arxiv_id, "pdf_url": self.pdf_url,
            "chunk_count": self.chunk_count, "source": self.source,
        }


async def discover_candidates(query: str, limit: int = 6) -> List[Dict[str, Any]]:
    """Search arXiv through the application's own client."""
    from app.services.arxiv_client import arxiv_client
    try:
        return await arxiv_client.search_works(query, limit=limit)
    except Exception as exc:
        logger.error("Discovery failed for query %r: %s", query, exc)
        return []


async def find_indexed_papers(db, min_chunks: int = 8) -> List[EvalDocument]:
    """Return already-indexed papers that have enough chunks to evaluate.

    Chunk counts come from Neo4j, not from `indexing_status`, because status is
    a claim about what happened while the chunk count is the thing retrieval
    actually depends on.
    """
    from sqlalchemy import select
    from app.models.paper import Paper
    from app.db.neo4j_client import neo4j_client

    rows = await db.execute(
        select(Paper.id, Paper.title, Paper.arxiv_id, Paper.pdf_url)
        .where(Paper.indexing_status == "indexed")
    )
    papers = {str(r[0]): (r[1], r[2], r[3]) for r in rows}
    if not papers:
        return []

    sess = await neo4j_client.get_session()
    async with sess:
        result = await sess.run(
            """
            MATCH (p:Paper)-[:HAS_CHUNK]->(c:Chunk)
            WHERE p.id IN $ids AND c.embedding IS NOT NULL
            RETURN p.id AS id, count(c) AS n
            """,
            ids=list(papers.keys()),
        )
        counts = {r["id"]: r["n"] for r in await result.data()}

    out: List[EvalDocument] = []
    for pid, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        if n < min_chunks:
            continue
        title, arxiv_id, pdf_url = papers[pid]
        out.append(EvalDocument(
            paper_id=pid, title=title or "", arxiv_id=arxiv_id,
            pdf_url=pdf_url, chunk_count=n, source="reused",
        ))
    return out


async def select_documents(
    db,
    queries: List[str],
    candidates_per_query: int,
    min_chunks: int,
    needed: int = 2,
    allow_existing: bool = True,
) -> List[EvalDocument]:
    """Assemble an evaluation corpus of `needed` distinct documents.

    Order of preference: ingest freshly discovered documents (exercising the
    full PDF → chunk → embed → index path), then top up from already-indexed
    documents so a run is still possible when arXiv or a PDF host is
    unreachable. Which path each document came from is recorded in `source`
    and reported, so results are never presented as "freshly ingested" when
    they were reused.
    """
    from evaluation.ingestion.evaluation_ingestion import ingest_document

    selected: List[EvalDocument] = []
    seen_titles: set[str] = set()

    for query in queries:
        if len(selected) >= needed:
            break
        for cand in await discover_candidates(query, candidates_per_query):
            if len(selected) >= needed:
                break
            title = (cand.get("title") or "").strip()
            key = title.lower()[:80]
            if not title or key in seen_titles:
                continue
            doc = await ingest_document(db, cand, min_chunks=min_chunks)
            if doc is not None:
                seen_titles.add(key)
                selected.append(doc)

    if len(selected) < needed and allow_existing:
        have = {d.paper_id for d in selected}
        for doc in await find_indexed_papers(db, min_chunks):
            if len(selected) >= needed:
                break
            key = (doc.title or "").lower()[:80]
            if doc.paper_id in have or key in seen_titles:
                continue
            seen_titles.add(key)
            selected.append(doc)

    return selected[:needed]
