import asyncio
import logging
import uuid
from typing import Dict, Any, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.paper import Paper
from app.db.neo4j_client import neo4j_client
from app.services.neo4j_service import neo4j_service
from app.services.semantic_scholar_client import semantic_scholar_client

logger = logging.getLogger(__name__)

def generate_external_id(provider: str, identifier: str) -> str:
    """Generate a stable deterministic UUID for an external paper."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"saira:external:{provider}:{identifier}"))

class CitationService:
    async def sync_paper_citations(self, db_session: AsyncSession, paper_id: str) -> None:
        """
        Fetch citations and references from Semantic Scholar and upsert them to Neo4j.
        This does not insert unverified papers into PostgreSQL.
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
            neo_sess = await neo4j_client.get_session()
            async with neo_sess:
                # 1. Upsert references (this paper cites them)
                for ref in references:
                    await self._upsert_and_link(neo_sess, ref, source_id=paper_id, target_id=None)
                    
                # 2. Upsert citations (they cite this paper)
                for cit in citations:
                    await self._upsert_and_link(neo_sess, cit, source_id=None, target_id=paper_id)
                    
            logger.info(f"Successfully synced {len(citations)} citations and {len(references)} references for Paper {paper_id}.")
        except Exception as e:
            logger.error(f"Failed to sync citations to Neo4j: {e}")

    async def _upsert_and_link(self, neo_sess, external_paper: Dict[str, Any], source_id: str | None, target_id: str | None) -> None:
        """
        Upsert external paper to Neo4j and create CITES relationship.
        If source_id is provided, source_id CITES external_paper.
        If target_id is provided, external_paper CITES target_id.
        """
        # Determine ID
        s2_id = external_paper.get("semantic_scholar_id")
        if not s2_id:
            return
            
        ext_id = generate_external_id("semantic_scholar", s2_id)
        
        has_pdf = bool(external_paper.get("pdf_url"))
        
        paper_dict = {
            "id": ext_id,
            "doi": external_paper.get("doi"),
            "arxiv_id": external_paper.get("arxiv_id"),
            "semantic_scholar_id": s2_id,
            "title": external_paper.get("title", "Untitled"),
            "publication_year": external_paper.get("publication_year"),
            "venue": external_paper.get("venue"),
        }
        
        query = """
        MERGE (p:Paper {id: $id})
        SET p.doi = $doi,
            p.arxiv_id = $arxiv_id,
            p.semantic_scholar_id = $semantic_scholar_id,
            p.title = $title,
            p.publication_year = $publication_year,
            p.venue = $venue,
            p.has_pdf = $has_pdf
        """
        await neo_sess.run(query, **paper_dict, has_pdf=has_pdf)
        
        if source_id:
            await neo4j_service.add_citation(neo_sess, source_id, ext_id)
        if target_id:
            await neo4j_service.add_citation(neo_sess, ext_id, target_id)

citation_service = CitationService()
