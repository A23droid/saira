import asyncio
import logging
import uuid
from typing import Dict, Any, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import delete

from app.models.knowledge import PaperCitation
from app.models.paper import Paper
from app.services.semantic_scholar_client import semantic_scholar_client

logger = logging.getLogger(__name__)

def generate_external_id(provider: str, identifier: str) -> str:
    """Generate a stable deterministic UUID for an external paper."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"saira:external:{provider}:{identifier}"))

class CitationService:
    async def sync_paper_citations(self, db_session: AsyncSession, paper_id: str) -> None:
        """Fetch this paper's citations and references and store the edges.

        External works are still NOT inserted into `papers` — that rule
        predates the migration and is worth keeping, because a work Semantic
        Scholar mentions has not been verified, fetched, or indexed. Their
        metadata is denormalized onto `paper_citations` instead, which is why
        that table carries `other_title` / `other_year` rather than a foreign
        key.
        """
        # Find paper to get its Semantic Scholar ID
        stmt = select(Paper).where(Paper.id == uuid.UUID(paper_id))
        db_paper = await db_session.scalar(stmt)
        if not db_paper:
            logger.error(f"Cannot sync citations: Paper {paper_id} not found in DB.")
            return

        s2_id = db_paper.semantic_scholar_id
        if not s2_id:
            logger.warning(f"Paper {paper_id} has no Semantic Scholar ID. Searching by title...")
            if db_paper.title:
                try:
                    s2_search = await semantic_scholar_client.search_works(db_paper.title, limit=1)
                    if s2_search and s2_search[0].get("semantic_scholar_id"):
                        s2_id = s2_search[0]["semantic_scholar_id"]
                        logger.info(f"Resolved S2 ID for citation sync: {s2_id}")
                except Exception as e:
                    logger.error(f"Failed to resolve S2 ID by title: {e}")
            
        if not s2_id:
            logger.error(f"Cannot sync citations: Could not resolve S2 ID for Paper {paper_id}.")
            return

        try:
            data = await semantic_scholar_client.get_citations_and_references(s2_id)
        except Exception as e:
            logger.error(f"Failed to fetch citations from Semantic Scholar: {e}")
            return
            
        citations = data.get("citations", [])
        references = data.get("references", [])
        
        if not citations and not references:
            logger.info(f"No citations or references found for Paper {paper_id}.")
            return

        try:
            pid = db_paper.id
            # Replace this paper's edges wholesale. Semantic Scholar's answer
            # is a snapshot, and merging would leave edges from a previous
            # snapshot that the source no longer reports.
            await db_session.execute(
                delete(PaperCitation).where(PaperCitation.paper_id == pid)
            )

            written = 0
            seen: set[tuple[str, str]] = set()

            # `references` are works this paper cites — outbound.
            for ref in references:
                if self._add_edge(db_session, pid, ref, "outbound", seen):
                    written += 1
            # `citations` are works citing this paper — inbound.
            for cit in citations:
                if self._add_edge(db_session, pid, cit, "inbound", seen):
                    written += 1

            await db_session.commit()
            logger.info(
                "citations_synced paper_id=%s inbound=%d outbound=%d written=%d",
                paper_id, len(citations), len(references), written,
            )
        except Exception as e:
            await db_session.rollback()
            logger.error("Failed to persist citations for %s: %s", paper_id, e)

    def _add_edge(
        self,
        db_session: AsyncSession,
        paper_id: Any,
        external_paper: Dict[str, Any],
        direction: str,
        seen: set,
    ) -> bool:
        """Stage one citation edge. Returns whether anything was added."""
        s2_id = external_paper.get("semantic_scholar_id")
        if not s2_id:
            # Without a stable identifier the edge cannot be deduplicated, and
            # a duplicate citation is worse than a missing one.
            return False

        ext_id = generate_external_id("semantic_scholar", s2_id)
        key = (direction, ext_id)
        if key in seen:
            return False
        seen.add(key)

        db_session.add(PaperCitation(
            paper_id=paper_id,
            direction=direction,
            other_id=ext_id,
            other_title=(external_paper.get("title") or "Untitled")[:1024],
            other_year=external_paper.get("publication_year"),
            other_doi=external_paper.get("doi"),
            other_arxiv_id=external_paper.get("arxiv_id"),
            other_semantic_scholar_id=s2_id,
            other_has_pdf=bool(external_paper.get("pdf_url")),
        ))
        return True


citation_service = CitationService()
