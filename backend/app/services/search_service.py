import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.paper import Paper
from app.models.project_paper import ProjectPaper
from app.schemas.paper import PaperCreate
from app.services.openalex_client import openalex_client


class SearchService:
    def _normalize_openalex_to_schema(self, work: Dict[str, Any]) -> PaperCreate:
        doi = work.get("doi")
        if doi and doi.startswith("https://doi.org/"):
            doi = doi.replace("https://doi.org/", "")

        arxiv_id = None
        for ext_id in work.get("ids", {}).values():
            if "arxiv" in str(ext_id).lower():
                arxiv_id = ext_id

        # Primary location venue
        venue = None
        primary_loc = work.get("primary_location") or {}
        if primary_loc.get("source"):
            venue = primary_loc["source"].get("display_name")

        pdf_url = None
        if primary_loc.get("pdf_url"):
            pdf_url = primary_loc.get("pdf_url")
        elif work.get("open_access", {}).get("oa_url"):
            pdf_url = work["open_access"]["oa_url"]

        # Rebuild abstract from OpenAlex inverted index
        abstract = ""
        inv_index = work.get("abstract_inverted_index")
        if inv_index:
            all_positions = [idx for positions in inv_index.values() for idx in positions]
            if all_positions:
                max_idx = max(all_positions)
                words = [""] * (max_idx + 1)
                for word, positions in inv_index.items():
                    for pos in positions:
                        words[pos] = word
                abstract = " ".join(words).strip()
        else:
            abstract = work.get("description", "")
        # Determine scholarly source dynamically
        source = "OpenAlex"
        ids = work.get("ids", {})
        if arxiv_id or "arxiv" in ids:
            source = "arXiv"
        elif "pmid" in ids or "pmcid" in ids:
            source = "PubMed"
        elif venue:
            venue_lower = venue.lower()
            if "ieee" in venue_lower:
                source = "IEEE"
            elif "pubmed" in venue_lower or "pmc" in venue_lower or "ncbi" in venue_lower:
                source = "PubMed"
            elif "acl anthology" in venue_lower or "association for computational linguistics" in venue_lower:
                source = "ACL Anthology"

        return PaperCreate(
            doi=doi,
            arxiv_id=arxiv_id,
            semantic_scholar_id=None,
            title=work.get("title") or "Untitled",
            abstract=abstract,
            publication_year=work.get("publication_year"),
            venue=venue,
            pdf_url=pdf_url,
            source=source,
            citation_count=work.get("cited_by_count"),
            reference_count=len(work.get("referenced_works", [])),
        )

    async def search_papers_external(self, query: str, limit: int = 20) -> List[dict]:
        works = await openalex_client.search_works(query, limit)
        results = []
        for work in works:
            if work.get("title"):
                normalized = self._normalize_openalex_to_schema(work)
                norm_dict = normalized.model_dump()
                openalex_id = work.get("id", "").split("/")[-1] if work.get("id") else None
                norm_dict["openalex_id"] = openalex_id
                results.append(norm_dict)
        return results

    async def ingest_paper(
        self, session: AsyncSession, openalex_id: str, project_id: Optional[uuid.UUID] = None
    ) -> Any:
        work = await openalex_client.get_work_by_id(openalex_id)
        normalized = self._normalize_openalex_to_schema(work)

        # Deduplication: DOI first, then arxiv_id
        db_paper = None
        conditions = []
        if normalized.doi:
            conditions.append(Paper.doi == normalized.doi)
        if normalized.arxiv_id:
            conditions.append(Paper.arxiv_id == normalized.arxiv_id)

        if conditions:
            stmt = select(Paper).where(or_(*conditions))
            db_paper = await session.scalar(stmt)

        if not db_paper:
            db_paper = Paper(**normalized.model_dump())
            session.add(db_paper)
            await session.commit()
            await session.refresh(db_paper)

        # Optionally add to project (idempotent)
        project_paper = None
        if project_id:
            stmt_assoc = select(ProjectPaper).where(
                ProjectPaper.project_id == project_id,
                ProjectPaper.paper_id == db_paper.id,
            )
            project_paper = await session.scalar(stmt_assoc)

            if not project_paper:
                project_paper = ProjectPaper(project_id=project_id, paper_id=db_paper.id)
                session.add(project_paper)
                await session.commit()
                await session.refresh(project_paper)

        return {"paper": db_paper, "project_paper": project_paper}


search_service = SearchService()
