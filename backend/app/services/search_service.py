import uuid
from typing import Any, Dict, List, Literal, Optional

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.paper import Paper
from app.models.project_paper import ProjectPaper
from app.schemas.paper import PaperCreate
from app.services.openalex_client import openalex_client
from app.services.arxiv_client import arxiv_client
from app.services.semantic_scholar_client import semantic_scholar_client

SearchSource = Literal["openalex", "arxiv", "semantic_scholar", "all"]


class SearchService:

    # ── Normalizers ──────────────────────────────────────────────────────────

    def _normalize_openalex(self, work: Dict[str, Any]) -> PaperCreate:
        doi = work.get("doi")
        if doi and doi.startswith("https://doi.org/"):
            doi = doi.replace("https://doi.org/", "")

        arxiv_id = None
        for ext_id in work.get("ids", {}).values():
            if "arxiv" in str(ext_id).lower():
                arxiv_id = ext_id

        venue = None
        primary_loc = work.get("primary_location") or {}
        if primary_loc.get("source"):
            venue = primary_loc["source"].get("display_name")

        pdf_url = None
        if primary_loc.get("pdf_url"):
            pdf_url = primary_loc["pdf_url"]
        elif work.get("open_access", {}).get("oa_url"):
            pdf_url = work["open_access"]["oa_url"]

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

        # Source label derived from metadata
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

    def _normalize_dict(self, raw: Dict[str, Any]) -> PaperCreate:
        """Convert a pre-normalized dict (from arXiv/S2 clients) to PaperCreate."""
        return PaperCreate(
            doi=raw.get("doi"),
            arxiv_id=raw.get("arxiv_id"),
            semantic_scholar_id=raw.get("semantic_scholar_id"),
            title=raw.get("title") or "Untitled",
            abstract=raw.get("abstract") or "",
            publication_year=raw.get("publication_year"),
            venue=raw.get("venue"),
            pdf_url=raw.get("pdf_url"),
            source=raw.get("source") or "Unknown",
            citation_count=raw.get("citation_count"),
            reference_count=raw.get("reference_count"),
        )

    # ── Search ───────────────────────────────────────────────────────────────

    async def search_papers_external(
        self,
        query: str,
        limit: int = 20,
        page: int = 1,
        source: SearchSource = "openalex",
    ) -> List[dict]:
        """
        Search one or all sources. Each result includes an `openalex_id`
        (for OpenAlex results) or appropriate ID fields for routing ingestion.
        """
        results: List[dict] = []

        async def _run_openalex() -> None:
            works = await openalex_client.search_works(query, limit, page)
            for work in works:
                if work.get("title"):
                    normalized = self._normalize_openalex(work)
                    d = normalized.model_dump()
                    d["openalex_id"] = work.get("id", "").split("/")[-1] if work.get("id") else None
                    results.append(d)

        async def _run_arxiv() -> None:
            works = await arxiv_client.search_works(query, limit)
            for work in works:
                normalized = self._normalize_dict(work)
                d = normalized.model_dump()
                d["openalex_id"] = None  # no OpenAlex ID for direct arXiv results
                results.append(d)

        async def _run_s2() -> None:
            works = await semantic_scholar_client.search_works(query, limit)
            for work in works:
                normalized = self._normalize_dict(work)
                d = normalized.model_dump()
                d["openalex_id"] = None
                results.append(d)

        if source == "openalex":
            await _run_openalex()
        elif source == "arxiv":
            await _run_arxiv()
        elif source == "semantic_scholar":
            await _run_s2()
        elif source == "all":
            # Fan out — collect all, deduplicate by DOI then arXiv ID
            per_source = limit // 3 or 10
            try:
                await _run_openalex()
            except Exception:
                pass
            try:
                await _run_arxiv()
            except Exception:
                pass
            try:
                await _run_s2()
            except Exception:
                pass
            results = _deduplicate(results)

        return results[:limit]

    # ── Ingestion ─────────────────────────────────────────────────────────────

    async def ingest_paper(
        self,
        session: AsyncSession,
        project_id: Optional[uuid.UUID] = None,
        # Exactly one of these must be provided
        openalex_id: Optional[str] = None,
        arxiv_id: Optional[str] = None,
        semantic_scholar_id: Optional[str] = None,
    ) -> Any:
        """
        Ingest a paper from a search source into the database.
        Deduplicates by DOI then arXiv ID then semantic_scholar_id.
        """
        if openalex_id:
            work = await openalex_client.get_work_by_id(openalex_id)
            normalized = self._normalize_openalex(work)
        elif arxiv_id:
            work = await arxiv_client.get_work_by_id(arxiv_id)
            normalized = self._normalize_dict(work)
        elif semantic_scholar_id:
            work = await semantic_scholar_client.get_work_by_id(semantic_scholar_id)
            normalized = self._normalize_dict(work)
        else:
            raise ValueError("One of openalex_id, arxiv_id, or semantic_scholar_id must be provided")

        # Deduplication: DOI → arXiv ID → Semantic Scholar ID
        db_paper = None
        conditions = []
        if normalized.doi:
            conditions.append(Paper.doi == normalized.doi)
        if normalized.arxiv_id:
            conditions.append(Paper.arxiv_id == normalized.arxiv_id)
        if normalized.semantic_scholar_id:
            conditions.append(Paper.semantic_scholar_id == normalized.semantic_scholar_id)

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


def _deduplicate(results: List[dict]) -> List[dict]:
    """Remove duplicate papers across sources by DOI or arXiv ID."""
    seen_dois: set = set()
    seen_arxiv: set = set()
    seen_s2: set = set()
    out = []
    for r in results:
        doi = r.get("doi")
        aid = r.get("arxiv_id")
        sid = r.get("semantic_scholar_id")

        if doi and doi in seen_dois:
            continue
        if aid and aid in seen_arxiv:
            continue
        if sid and sid in seen_s2:
            continue

        if doi:
            seen_dois.add(doi)
        if aid:
            seen_arxiv.add(aid)
        if sid:
            seen_s2.add(sid)
        out.append(r)
    return out


search_service = SearchService()
