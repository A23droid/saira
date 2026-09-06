import asyncio
import re
import uuid
import logging
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
from app.services.pdf_validator import pdf_validator
from app.db.neo4j_client import neo4j_client
from app.services.neo4j_service import neo4j_service

logger = logging.getLogger(__name__)

# Strong references to background tasks, so they are not garbage collected
# mid-flight. Entries are discarded by each task's done-callback.
_BACKGROUND_TASKS: set = set()

SearchSource = Literal["openalex", "arxiv", "semantic_scholar", "all"]
MAX_CANDIDATE_PAGES = 5
CONCURRENCY_LIMIT = 10

def _clean_pdf_url(url: Optional[str]) -> Optional[str]:
    """Ensure the URL is likely a PDF and not a generic landing page."""
    if not url:
        return None
    
    url_lower = url.lower()
    if url_lower.endswith(".pdf") or "/pdf/" in url_lower:
        return url
        
    if "semanticscholar.org/paper/" in url_lower or "arxiv.org/abs/" in url_lower:
        return None
        
    if "pdf" in url_lower or "pmc/articles" in url_lower:
        return url
        
    return None

class SearchService:

    # ── Normalizers ──────────────────────────────────────────────────────────

    def _normalize_openalex(self, work: Dict[str, Any]) -> Dict[str, Any]:
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

        candidate_urls = []
        if primary_loc.get("pdf_url"):
            candidate_urls.append(primary_loc["pdf_url"])
        if work.get("open_access", {}).get("oa_url"):
            candidate_urls.append(work["open_access"]["oa_url"])
        if primary_loc.get("landing_page_url"):
            candidate_urls.append(primary_loc["landing_page_url"])
            
        candidate_urls = [u for u in candidate_urls if u]

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

        return {
            "doi": doi,
            "arxiv_id": arxiv_id,
            "semantic_scholar_id": None,
            "title": work.get("title") or "Untitled",
            "abstract": abstract,
            "publication_year": work.get("publication_year"),
            "venue": venue,
            "candidate_urls": candidate_urls,
            "pdf_url": None,
            "source": source,
            "citation_count": work.get("cited_by_count"),
            "reference_count": len(work.get("referenced_works", [])),
        }

    def _normalize_dict(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Convert a pre-normalized dict (from arXiv/S2 clients) to intermediate dict."""
        candidate_urls = []
        if raw.get("pdf_url"):
            candidate_urls.append(raw.get("pdf_url"))
            
        if raw.get("arxiv_id"):
            candidate_urls.append(f"https://arxiv.org/pdf/{raw.get('arxiv_id')}.pdf")
            
        return {
            "doi": raw.get("doi"),
            "arxiv_id": raw.get("arxiv_id"),
            "semantic_scholar_id": raw.get("semantic_scholar_id"),
            "title": raw.get("title") or "Untitled",
            "abstract": raw.get("abstract") or "",
            "publication_year": raw.get("publication_year"),
            "venue": raw.get("venue"),
            "candidate_urls": candidate_urls,
            "pdf_url": None,
            "source": raw.get("source") or "Unknown",
            "citation_count": raw.get("citation_count"),
            "reference_count": raw.get("reference_count"),
        }

    # ── Search ───────────────────────────────────────────────────────────────

    async def _validate_paper_candidates(self, paper: dict, semaphore: asyncio.Semaphore) -> Optional[dict]:
        """Validates a single paper's candidate PDFs. Returns the paper with pdf_url set if valid, else None."""
        if not _is_valid_paper(paper):
            return None

        async with semaphore:
            valid_pdf = await pdf_validator.find_valid_pdf(paper.get("candidate_urls", []))
            if valid_pdf:
                paper["pdf_url"] = valid_pdf
                # Remove candidate_urls to match expected PaperCreate shape
                paper.pop("candidate_urls", None)
                return paper
            else:
                logger.info(f"Paper '{paper.get('title')}' filtered out: No valid PDF candidates.")
                return None

    async def _run_provider_search(self, provider_name: str, query: str, limit: int, start_page: int) -> List[dict]:
        """Fetches from a single provider until `limit` valid papers are found or max pages hit."""
        valid_results = []
        current_page = start_page
        pages_fetched = 0
        semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)

        while len(valid_results) < limit and pages_fetched < MAX_CANDIDATE_PAGES:
            pages_fetched += 1
            works = []
            if provider_name == "openalex":
                works = await openalex_client.search_works(query, limit, current_page)
            elif provider_name == "arxiv":
                works = await arxiv_client.search_works(query, limit, current_page)
            elif provider_name == "semantic_scholar":
                works = await semantic_scholar_client.search_works(query, limit, current_page)
                
            if not works:
                break

            candidates = []
            for work in works:
                if provider_name == "openalex" and not (work.get("title") and work.get("id")):
                    continue
                    
                if provider_name == "openalex":
                    d = self._normalize_openalex(work)
                    d["openalex_id"] = work.get("id").split("/")[-1]
                else:
                    d = self._normalize_dict(work)
                    d["openalex_id"] = None
                    
                d["provider"] = provider_name
                candidates.append(d)

            # Parallel validation
            tasks = [self._validate_paper_candidates(c, semaphore) for c in candidates]
            validated = await asyncio.gather(*tasks)
            
            for v in validated:
                if v is not None:
                    valid_results.append(v)
                    if len(valid_results) >= limit:
                        break
                        
            current_page += 1

        return valid_results

    async def search_papers_external(
        self,
        session: AsyncSession,
        query: str,
        limit: int = 20,
        page: int = 1,
        source: SearchSource = "openalex",
    ) -> List[dict]:
        """
        Search one or all sources in parallel, validate PDFs, and deduplicate.
        """
        results: List[dict] = []

        if source == "all":
            # Fan out in parallel
            tasks = [
                self._run_provider_search("openalex", query, limit, page),
                self._run_provider_search("arxiv", query, limit, page),
                self._run_provider_search("semantic_scholar", query, limit, page)
            ]
            parallel_results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in parallel_results:
                if isinstance(res, list):
                    results.extend(res)
            
            results = _deduplicate(results)
        else:
            results = await self._run_provider_search(source, query, limit, page)

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

    async def get_similar_papers(self, session: AsyncSession, paper: Paper, limit: int = 5) -> List[Paper]:
        """
        Orchestrates similar papers lookup with fallbacks, PDF validation, and pagination.
        Saves valid candidates to the database so they can be viewed.
        """
        valid_results = []
        candidates = []
        semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)

        # 0. Neo4j Graph Candidates
        try:
            neo_sess = await neo4j_client.get_session()
            async with neo_sess:
                graph_candidates = await neo4j_service.get_similar_candidates(neo_sess, str(paper.id), limit=limit*2)
                for c in graph_candidates:
                    c["provider"] = "neo4j_graph"
                    candidates.append(c)
                if graph_candidates:
                    logger.info(f"Neo4j graph candidates: found {len(graph_candidates)}")
        except Exception as e:
            logger.error(f"Failed to fetch Neo4j graph candidates: {e}")

        # 1. Semantic Scholar Fallback Chain
        s2_identifier = None
        if paper.semantic_scholar_id:
            s2_identifier = paper.semantic_scholar_id
        elif paper.arxiv_id:
            clean_arxiv = paper.arxiv_id.split("/")[-1]
            s2_identifier = f"ARXIV:{clean_arxiv}"
        elif paper.doi:
            s2_identifier = f"DOI:{paper.doi}"
            
        logger.info(f"Finding similar papers for Paper ID: {paper.id}")

        if not s2_identifier and paper.title:
            try:
                s2_search = await semantic_scholar_client.search_works(paper.title, limit=1)
                if s2_search and s2_search[0].get("semantic_scholar_id"):
                    s2_identifier = s2_search[0]["semantic_scholar_id"]
                    logger.info(f"Resolved S2 ID from title: {s2_identifier}")
            except Exception as e:
                logger.error(f"Failed to resolve S2 ID by title: {e}")

        if s2_identifier:
            try:
                works = await semantic_scholar_client.get_similar_works(s2_identifier, limit=limit*3)
                if works:
                    logger.info(f"Semantic Scholar lookup: success (found {len(works)})")
                    for work in works:
                        d = self._normalize_dict(work)
                        d["provider"] = "semantic_scholar"
                        candidates.append(d)
                else:
                    logger.info("Semantic Scholar lookup: zero results")
            except Exception as e:
                logger.error(f"Semantic Scholar lookup: failed ({e})")

        # 2. OpenAlex Fallback
        if not candidates:
            oa_identifier = None
            if paper.doi:
                oa_identifier = f"https://doi.org/{paper.doi}"
            elif paper.title:
                try:
                    oa_search = await openalex_client.search_works(paper.title, limit=1)
                    if oa_search and oa_search[0].get("id"):
                        oa_identifier = oa_search[0]["id"].split("/")[-1]
                        logger.info(f"Resolved OpenAlex ID from title: {oa_identifier}")
                except Exception as e:
                    logger.error(f"Failed to resolve OpenAlex ID by title: {e}")

            if oa_identifier:
                try:
                    works = await openalex_client.get_similar_works(oa_identifier, limit=limit*3)
                    if works:
                        logger.info(f"OpenAlex fallback: success (found {len(works)})")
                        for work in works:
                            if work.get("title") and work.get("id"):
                                d = self._normalize_openalex(work)
                                d["provider"] = "openalex"
                                candidates.append(d)
                    else:
                        logger.info("OpenAlex fallback: zero results")
                except Exception as e:
                    logger.error(f"OpenAlex fallback: failed ({e})")
        
        # Deduplicate candidates and remove the current paper
        deduped = []
        seen = set()
        
        # Avoid recommending the source paper itself
        if paper.doi: seen.add(paper.doi)
        if paper.arxiv_id: seen.add(paper.arxiv_id)
        if paper.semantic_scholar_id: seen.add(paper.semantic_scholar_id)
        
        for c in candidates:
            # Check identifiers
            is_dup = False
            for key in ["doi", "arxiv_id", "semantic_scholar_id"]:
                val = c.get(key)
                if val:
                    if val in seen:
                        is_dup = True
                        break
                    
            norm_title = _normalize_title(c.get("title", ""))
            if norm_title == _normalize_title(paper.title):
                is_dup = True
                
            if not is_dup:
                deduped.append(c)
                for key in ["doi", "arxiv_id", "semantic_scholar_id"]:
                    val = c.get(key)
                    if val:
                        seen.add(val)
        
        # Validate PDFs concurrently
        logger.info(f"Final candidates: {len(deduped)}")
        tasks = [self._validate_paper_candidates(c, semaphore) for c in deduped]
        validated = await asyncio.gather(*tasks)
        
        db_papers = []
        for v in validated:
            if v is not None:
                # Save to DB if not exists
                conditions = []
                if v.get("doi"): conditions.append(Paper.doi == v["doi"])
                if v.get("arxiv_id"): conditions.append(Paper.arxiv_id == v["arxiv_id"])
                if v.get("semantic_scholar_id"): conditions.append(Paper.semantic_scholar_id == v["semantic_scholar_id"])
                if v.get("title"): conditions.append(Paper.title.ilike(v["title"]))
                
                db_paper = None
                if conditions:
                    stmt = select(Paper).where(or_(*conditions))
                    db_paper = await session.scalar(stmt)
                    
                if not db_paper:
                    v.pop("provider", None)
                    v.pop("openalex_id", None)
                    v.pop("local_id", None)
                    v.pop("saved_project_ids", None)
                    db_paper = Paper(**v)
                    session.add(db_paper)
                    await session.commit()
                    await session.refresh(db_paper)
                
                db_papers.append(db_paper)
                if len(db_papers) >= limit:
                    break

        logger.info(f"Final valid papers: {len(db_papers)}")
        return db_papers

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
            normalized_dict = self._normalize_openalex(work)
        elif arxiv_id:
            work = await arxiv_client.get_work_by_id(arxiv_id)
            normalized_dict = self._normalize_dict(work)
        elif semantic_scholar_id:
            work = await semantic_scholar_client.get_work_by_id(semantic_scholar_id)
            normalized_dict = self._normalize_dict(work)
        else:
            raise ValueError("One of openalex_id, arxiv_id, or semantic_scholar_id must be provided")

        # Validate PDF before ingestion
        valid_pdf = await pdf_validator.find_valid_pdf(normalized_dict.get("candidate_urls", []))
        normalized_dict["pdf_url"] = valid_pdf
        normalized_dict.pop("candidate_urls", None)
        
        normalized = PaperCreate(**normalized_dict)

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
            if not valid_pdf:
                # A paper with no reachable PDF is still worth having as
                # metadata — it just cannot support full-text Ask AI. Saying so
                # in the status beats refusing the save and losing the paper.
                db_paper.indexing_status = "pdf_unavailable"
                db_paper.indexing_error = "No accessible PDF source found."
            session.add(db_paper)
            await session.commit()
            await session.refresh(db_paper)

        async def _sync_to_neo4j(p_dict):
            try:
                neo_sess = await neo4j_client.get_session()
                async with neo_sess:
                    await neo4j_service.upsert_paper(neo_sess, p_dict)
            except Exception as e:
                logger.error(f"Failed to sync paper {p_dict.get('id')} to Neo4j: {e}")

        paper_dict = {
            "id": str(db_paper.id),
            "doi": db_paper.doi,
            "arxiv_id": db_paper.arxiv_id,
            "semantic_scholar_id": db_paper.semantic_scholar_id,
            "title": db_paper.title,
            "publication_year": db_paper.publication_year,
            "venue": db_paper.venue,
            "citation_count": db_paper.citation_count,
        }
        # asyncio holds only a weak reference to a running task, so a
        # fire-and-forget `create_task` can be collected before it does any
        # work. Keep a strong reference until it completes.
        task = asyncio.create_task(_sync_to_neo4j(paper_dict))
        _BACKGROUND_TASKS.add(task)
        task.add_done_callback(_BACKGROUND_TASKS.discard)

        # Indexing is started here, awaited, rather than nested inside that
        # task: `ensure_indexed` returns as soon as the job is queued (it owns
        # both the dedup guard and a strong reference to the running job), so
        # this does not block the request on a PDF download — but it does
        # guarantee the job is actually started before the response is sent.
        if db_paper.pdf_url or db_paper.indexing_status not in ("pdf_unavailable",):
            from app.services.indexing_jobs import ensure_indexed

            await ensure_indexed(db_paper.id)

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
    return re.sub(r'[^a-z0-9]', '', title.lower())

def _deduplicate(results: List[dict]) -> List[dict]:
    """Remove duplicate papers across sources by IDs or normalized title + year."""
    seen_dois: set = set()
    seen_arxiv: set = set()
    seen_s2: set = set()
    seen_titles: set = set()
    out = []
    
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
    """
    provider = paper.get("provider")
    title = paper.get("title")
    
    if not title or len(title.strip()) < 3:
        return False

    if provider == "openalex":
        if not paper.get("openalex_id"):
            return False
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

    year = paper.get("publication_year")
    if year and (year < 1800 or year > 2100):
        return False
        
    return True


search_service = SearchService()
