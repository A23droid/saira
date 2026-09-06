"""
Ingest evaluation documents through SAIRA's real pipeline, then verify the
ingestion invariants the RAG objective depends on.

Nothing here reimplements parsing, chunking, or embedding — it calls
`research_indexer` exactly as the application does, then inspects the result.
That separation is the point: the harness checks the product's output rather
than its own.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


async def ingest_document(db, candidate: Dict[str, Any], min_chunks: int = 8):
    """Persist a discovered paper and run the real indexing pipeline over it."""
    from sqlalchemy import or_, select

    from app.models.paper import Paper
    from app.schemas.paper import PaperCreate
    from app.services.pdf_validator import pdf_validator
    from app.services.research_indexer import research_indexer
    from evaluation.discovery.document_discovery import EvalDocument

    title = (candidate.get("title") or "").strip()
    arxiv_id = candidate.get("arxiv_id")

    conditions = []
    if arxiv_id:
        conditions.append(Paper.arxiv_id == arxiv_id)
    if title:
        conditions.append(Paper.title.ilike(title))
    paper = await db.scalar(select(Paper).where(or_(*conditions))) if conditions else None

    if paper is None:
        pdf_url = await pdf_validator.find_valid_pdf(
            [u for u in [candidate.get("pdf_url"),
                         f"https://arxiv.org/pdf/{arxiv_id}.pdf" if arxiv_id else None] if u]
        )
        if not pdf_url:
            logger.info("Skipping %r: no accessible PDF.", title[:60])
            return None
        payload = PaperCreate(
            doi=candidate.get("doi"), arxiv_id=arxiv_id,
            semantic_scholar_id=candidate.get("semantic_scholar_id"),
            title=title, abstract=candidate.get("abstract") or "",
            publication_year=candidate.get("publication_year"),
            venue=candidate.get("venue"), pdf_url=pdf_url,
            source=candidate.get("source") or "arXiv",
            citation_count=candidate.get("citation_count"),
            reference_count=candidate.get("reference_count"),
        )
        paper = Paper(**payload.model_dump())
        db.add(paper)
        await db.commit()
        await db.refresh(paper)

    try:
        await research_indexer.index_paper(db, str(paper.id))
    except Exception as exc:
        logger.error("Indexing raised for %s: %s", paper.id, exc)

    await db.refresh(paper)
    chunk_count = await count_chunks(str(paper.id))
    if chunk_count < min_chunks:
        logger.info(
            "Skipping %r: only %d chunks (status=%s, err=%s)",
            title[:50], chunk_count, paper.indexing_status, paper.indexing_error,
        )
        return None

    return EvalDocument(
        paper_id=str(paper.id), title=paper.title or title,
        arxiv_id=paper.arxiv_id, pdf_url=paper.pdf_url,
        chunk_count=chunk_count, source="discovered",
    )


async def count_chunks(paper_id: str) -> int:
    from app.db.neo4j_client import neo4j_client
    sess = await neo4j_client.get_session()
    async with sess:
        res = await sess.run(
            "MATCH (:Paper {id:$id})-[:HAS_CHUNK]->(c:Chunk) RETURN count(c) AS n",
            id=paper_id,
        )
        rec = await res.single()
        return rec["n"] if rec else 0


async def verify_ingestion(paper_id: str) -> Dict[str, Any]:
    """Check every ingestion invariant from the RAG objective.

    Each check is reported independently, so a failure identifies which link in
    PDF → parse → chunk → embed → index broke rather than collapsing into
    "ingestion failed".
    """
    from app.db.neo4j_client import neo4j_client

    sess = await neo4j_client.get_session()
    async with sess:
        rows = await (await sess.run(
            """
            MATCH (p:Paper {id:$id})-[:HAS_CHUNK]->(c:Chunk)
            RETURN c.id AS id, c.page AS page, c.chunk_index AS idx,
                   c.paper_id AS pid, c.text AS text,
                   size(c.embedding) AS dim
            ORDER BY c.chunk_index
            """, id=paper_id)).data()

        cross = await (await sess.run(
            """
            MATCH (p:Paper {id:$id})-[:HAS_CHUNK]->(c:Chunk)
            WHERE c.paper_id <> $id
            RETURN count(c) AS n
            """, id=paper_id)).single()

    n = len(rows)
    ids = [r["id"] for r in rows]
    idxs = [r["idx"] for r in rows if r["idx"] is not None]
    pages = [r["page"] for r in rows if r["page"] is not None]
    dims = {r["dim"] for r in rows}
    texts = [r["text"] or "" for r in rows]

    checks = {
        "has_chunks": n > 0,
        "chunk_ids_unique": len(set(ids)) == n,
        "chunk_index_unique": len(set(idxs)) == len(idxs),
        "chunk_index_contiguous": sorted(idxs) == list(range(len(idxs))) if idxs else False,
        "page_numbers_present": len(pages) == n,
        "page_order_monotonic": pages == sorted(pages) if pages else False,
        "all_embeddings_384": dims == {384} if dims else False,
        "no_null_embeddings": None not in dims,
        "paper_id_matches": (cross["n"] if cross else 0) == 0,
        "no_empty_text": all(t.strip() for t in texts),
        "text_not_duplicated": len(set(texts)) >= max(1, int(n * 0.9)),
    }

    return {
        "paper_id": paper_id,
        "chunk_count": n,
        "distinct_pages": len(set(pages)),
        "embedding_dims": sorted(d for d in dims if d is not None),
        "duplicate_text_chunks": n - len(set(texts)),
        "cross_document_chunks": cross["n"] if cross else 0,
        "checks": checks,
        "all_passed": all(checks.values()),
        "failed_checks": [k for k, v in checks.items() if not v],
    }
