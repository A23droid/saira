import asyncio
import re
import uuid
from typing import Any, Dict, List, Literal, Optional

from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.paper import Paper
from app.models.project_paper import ProjectPaper
from app.schemas.paper import PaperCreate
from app.services.openalex_client import openalex_client
from app.services.arxiv_client import arxiv_client
from app.services.semantic_scholar_client import semantic_scholar_client

SearchSource = Literal["openalex", "arxiv", "semantic_scholar", "all"]


def _clean_pdf_url(url: Optional[str]) -> Optional[str]:
    """Ensure the URL is likely a PDF and not a generic landing page."""
    if not url:
        return None
    
    url_lower = url.lower()
    # If it ends with .pdf or contains /pdf/, it's likely a PDF
    if url_lower.endswith(".pdf") or "/pdf/" in url_lower:
        return url
        
    # If it's a known publisher landing page (e.g., Semantic Scholar, arXiv abs), it's not a direct PDF
    if "semanticscholar.org/paper/" in url_lower or "arxiv.org/abs/" in url_lower:
        return None
        
    # Many OpenAlex oa_url values are just HTML pages (e.g. PMC articles, publisher HTML)
    # We will accept them if they contain 'pdf' or 'pmc/articles' (often PMC provides a PDF or iframe-able HTML).
    if "pdf" in url_lower or "pmc/articles" in url_lower:
        return url
        
    return None

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
            
        pdf_url = _clean_pdf_url(pdf_url)

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
            pdf_url=_clean_pdf_url(raw.get("pdf_url")),
            source=raw.get("source") or "Unknown",
            citation_count=raw.get("citation_count"),
            reference_count=raw.get("reference_count"),
        )

    # ── Search ───────────────────────────────────────────────────────────────

    async def search_papers_external(
        self,
        session: AsyncSession,
        query: str,
        limit: int = 20,
        page: int = 1,
        source: SearchSource = "openalex",
    ) -> List[dict]:
        """
        Search one or all sources in parallel, validate results, and deduplicate.
        """
        results: List[dict] = []

        async def _run_openalex() -> List[dict]:
            out = []
            works = await openalex_client.search_works(query, limit, page)
            for work in works:
                if work.get("title") and work.get("id"):
                    normalized = self._normalize_openalex(work)
                    d = normalized.model_dump()
                    d["openalex_id"] = work.get("id").split("/")[-1]
                    d["provider"] = "openalex"
                    if _is_valid_paper(d):
                        out.append(d)
            return out

        async def _run_arxiv() -> List[dict]:
            out = []
            works = await arxiv_client.search_works(query, limit, page)
            for work in works:
                normalized = self._normalize_dict(work)
                d = normalized.model_dump()
                d["openalex_id"] = None
                d["provider"] = "arxiv"
                if _is_valid_paper(d):
                    out.append(d)
            return out

        async def _run_s2() -> List[dict]:
            out = []
            works = await semantic_scholar_client.search_works(query, limit, page)
            for work in works:
                normalized = self._normalize_dict(work)
                d = normalized.model_dump()
                d["openalex_id"] = None
                d["provider"] = "semantic_scholar"
                if _is_valid_paper(d):
                    out.append(d)
            return out

        if source == "openalex":
            results = await _run_openalex()
        elif source == "arxiv":
            results = await _run_arxiv()
        elif source == "semantic_scholar":
            results = await _run_s2()
        elif source == "all":
            # Fan out in parallel
            tasks = [_run_openalex(), _run_arxiv(), _run_s2()]
            parallel_results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in parallel_results:
                if isinstance(res, list):
                    results.extend(res)
            
            results = _deduplicate(results)

        # Apply limit after validation and deduplication
        results = results[:limit]
        
        # Check local DB for matches to populate local_id and saved_project_ids
        for r in results:
            r["local_id"] = None
            r["saved_project_ids"] = []
            
            conditions = []
            if r.get("doi"):
                conditions.append(Paper.doi == r["doi"])
            if r.get("arxiv_id"):
                conditions.append(Paper.arxiv_id == r["arxiv_id"])
            if r.get("semantic_scholar_id"):
                conditions.append(Paper.semantic_scholar_id == r["semantic_scholar_id"])
            if r.get("title"):
                conditions.append(Paper.title.ilike(r["title"]))
                
            if conditions:
                stmt = select(Paper).options(selectinload(Paper.project_papers)).where(or_(*conditions))
                db_paper = await session.scalar(stmt)
                if db_paper:
                    r["local_id"] = str(db_paper.id)
                    r["saved_project_ids"] = [str(pp.project_id) for pp in db_paper.project_papers]

        return results

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

        # Deduplication: DOI → arXiv ID → Semantic Scholar ID → Title
        db_paper = None
        conditions = []
        if normalized.doi:
            conditions.append(Paper.doi == normalized.doi)
        if normalized.arxiv_id:
            conditions.append(Paper.arxiv_id == normalized.arxiv_id)
        if normalized.semantic_scholar_id:
            conditions.append(Paper.semantic_scholar_id == normalized.semantic_scholar_id)
        if normalized.title:
            conditions.append(Paper.title.ilike(normalized.title))

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


def _normalize_title(title: str) -> str:
    """Normalize title for fuzzy deduplication."""
    if not title:
        return ""
    # lower case, remove non-alphanumeric, strip spaces
    return re.sub(r'[^a-z0-9]', '', title.lower())

def _deduplicate(results: List[dict]) -> List[dict]:
    """Remove duplicate papers across sources by IDs or normalized title + year."""
    seen_dois: set = set()
    seen_arxiv: set = set()
    seen_s2: set = set()
    seen_titles: set = set()
    out = []
    
    # Sort results to prefer OpenAlex (usually richer metadata) if available
    # Since we can't guarantee order easily from gather, we just process as they come, 
    # but could sort by source preference.
    for r in results:
        doi = r.get("doi")
        aid = r.get("arxiv_id")
        sid = r.get("semantic_scholar_id")
        
        norm_title = _normalize_title(r.get("title", ""))
        year = r.get("publication_year")
        title_key = f"{norm_title}_{year}" if norm_title and year else None

        if doi and doi in seen_dois:
            continue
        if aid and aid in seen_arxiv:
            continue
        if sid and sid in seen_s2:
            continue
        if title_key and title_key in seen_titles:
            continue

        if doi:
            seen_dois.add(doi)
        if aid:
            seen_arxiv.add(aid)
        if sid:
            seen_s2.add(sid)
        if title_key:
            seen_titles.add(title_key)
            
        out.append(r)
    return out

def _is_valid_paper(paper: dict) -> bool:
    """
    Validate that the paper has sufficient authoritative metadata and content.
    Validation is provider-aware.
    """
    provider = paper.get("provider")
    title = paper.get("title")
    
    if not title or len(title.strip()) < 3:
        return False

    if provider == "openalex":
        if not paper.get("openalex_id"):
            return False
        # Require title and meaningful abstract for scholarly works
        if not paper.get("abstract") or len(paper.get("abstract").strip()) < 50:
            return False

    elif provider == "arxiv":
        if not paper.get("arxiv_id"):
            return False
        if not paper.get("abstract") or len(paper.get("abstract").strip()) < 50:
            return False

    elif provider == "semantic_scholar":
        if not paper.get("semantic_scholar_id"):
            return False

    # Check for valid year if present
    year = paper.get("publication_year")
    if year and (year < 1800 or year > 2100):
        return False
        
    return True



search_service = SearchService()
