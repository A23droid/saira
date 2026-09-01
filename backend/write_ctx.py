CODE = r'''import hashlib
import math
import re
import uuid
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.project_paper import ProjectPaper
from app.models.paper import Paper


def _tokenize(text: str) -> List[str]:
    """Lowercase word tokenizer for BM25."""
    return re.findall(r'\b[a-z]{2,}\b', text.lower())


def _bm25_score(qt, dt, n, df, k1=1.5, b=0.75, avg=150.0):
    tf = Counter(dt)
    score = 0.0
    for token in set(qt):
        if token not in tf:
            continue
        nt = df.get(token, 0)
        if nt == 0:
            continue
        idf = math.log((n - nt + 0.5) / (nt + 0.5) + 1.0)
        tfd = tf[token] * (k1 + 1) / (tf[token] + k1 * (1 - b + b * len(dt) / avg))
        score += idf * tfd
    return score


def _rank_papers_by_query(query: str, papers: List[Dict], top_k: int = 5) -> List[Dict]:
    """BM25 keyword ranking. Returns all papers if len <= top_k."""
    if len(papers) <= top_k:
        return papers
    qt = _tokenize(query)
    if not qt:
        return papers[:top_k]
    dts = [_tokenize(p.get("title") or "") * 3 + _tokenize(p.get("abstract") or "") for p in papers]
    df: Counter = Counter()
    for dt in dts:
        for t in set(dt):
            df[t] += 1
    avg = sum(len(t) for t in dts) / max(len(dts), 1)
    scored = [(_bm25_score(qt, dt, len(papers), df, avg=avg), i, p) for i, (p, dt) in enumerate(zip(papers, dts))]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [p for _, _, p in scored[:top_k]]


def compute_paper_set_version(paper_ids: List[str]) -> str:
    """Return SHA-256 fingerprint of sorted paper IDs."""
    return hashlib.sha256(",".join(sorted(str(pid) for pid in paper_ids)).encode()).hexdigest()


class ProjectContextBuilder:
    """Builds AI-ready context from a user project workspace. All methods are user-scoped."""

    async def _fetch_project_with_papers(self, session, project_id, user_id=None):
        stmt = (
            select(Project)
            .options(
                selectinload(Project.project_papers).selectinload(ProjectPaper.paper).selectinload(Paper.analysis),
                selectinload(Project.project_papers).selectinload(ProjectPaper.notes),
                selectinload(Project.project_papers).selectinload(ProjectPaper.highlights),
                selectinload(Project.project_papers).selectinload(ProjectPaper.reading_progress),
            )
            .where(Project.id == project_id)
        )
        if user_id is not None:
            stmt = stmt.where(Project.user_id == user_id)
        return await session.scalar(stmt)

    def _pp_to_dict(self, pp) -> Dict[str, Any]:
        paper = pp.paper
        auths = paper.authors if hasattr(paper, "authors") and paper.authors else []
        if isinstance(auths, list):
            authors_str = ", ".join(a.get("name", "") if isinstance(a, dict) else str(a) for a in auths)
        else:
            authors_str = str(auths)
        return {
            "id": str(paper.id),
            "title": paper.title,
            "abstract": paper.abstract,
            "authors": authors_str,
            "publication_year": paper.publication_year,
            "year": paper.publication_year,
            "venue": paper.venue,
            "source": paper.source,
            "doi": paper.doi,
            "arxiv_id": paper.arxiv_id,
            "semantic_scholar_id": paper.semantic_scholar_id,
            "citation_count": paper.citation_count,
            "status": pp.status or "unread",
            "favorite": pp.favorite,
            "summary_tldr": paper.analysis.summary_tldr if paper.analysis else None,
            "notes": [n.content for n in (pp.notes or [])],
            "highlights": [h.content for h in (pp.highlights or [])],
        }

    async def build_context(self, session, project_id, user_id=None) -> str:
        """Build bounded text context for project QA (all papers, no retrieval)."""
        project = await self._fetch_project_with_papers(session, project_id, user_id)
        if not project:
            return "Project not found or access denied."
        lines = [
            f"Project: {project.name}",
            f"Description: {project.description or 'None'}",
            "",
            "--- PAPERS IN WORKSPACE ---",
        ]
        if not project.project_papers:
            lines.append("No papers in this project yet.")
        else:
            for pp in project.project_papers:
                paper = pp.paper
                lines.append(f"\nPaper: {paper.title} ({paper.publication_year})")
                if paper.analysis and paper.analysis.summary_tldr:
                    lines.append(f"Summary: {paper.analysis.summary_tldr}")
                elif paper.abstract:
                    lines.append(f"Abstract: {paper.abstract[:300]}")
                for n in (pp.notes or []):
                    lines.append(f"User Note: {n.content}")
                for h in (pp.highlights or []):
                    lines.append(f"Highlight: {h.content}")
        return "\n".join(lines)

    async def build_retrieval_context(self, session, project_id, user_id, query: str, top_k: int = 5):
        """BM25 retrieval-augmented context. Returns (context_str, ranked_papers, paper_index)."""
        project = await self._fetch_project_with_papers(session, project_id, user_id)
        if not project:
            return "Project not found.", [], {}
        all_dicts = [self._pp_to_dict(pp) for pp in project.project_papers]
        ranked = _rank_papers_by_query(query, all_dicts, top_k=top_k)
        paper_index = {p["id"]: {"title": p["title"], "year": p.get("year")} for p in all_dicts}
        lines = [
            f"Project: {project.name}",
            f"Papers: {len(all_dicts)} total, top {len(ranked)} retrieved for this query:",
            "",
        ]
        for i, p in enumerate(ranked, 1):
            lines.append(f"Paper {i} (ID: {p['id']})")
            lines.append(f"Title: {p['title']}")
            lines.append(f"Authors: {p.get('authors', 'N/A')}")
            lines.append(f"Year: {p.get('year', 'N/A')}")
            if p.get("summary_tldr"):
                lines.append(f"Summary: {p['summary_tldr']}")
            elif p.get("abstract"):
                ab = p["abstract"]
                lines.append(f"Abstract: {ab[:400]}")
            for n in p.get("notes", [])[:3]:
                lines.append(f"Note: {n}")
            lines.append("")
        return "\n".join(lines), ranked, paper_index

    async def get_all_paper_dicts(self, session, project_id, user_id):
        """Fetch all papers as dicts for lit review pipeline. Returns (project, [dicts])."""
        project = await self._fetch_project_with_papers(session, project_id, user_id)
        if not project:
            return None, []
        return project, [self._pp_to_dict(pp) for pp in project.project_papers]


project_context_builder = ProjectContextBuilder()
'''

with open("app/services/project_context.py", "w", encoding="utf-8") as f:
    f.write(CODE)

LRS_CODE = r'''import asyncio
import logging
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.literature_review import LiteratureReview
from app.schemas.ai import LiteratureReviewContent, LiteratureReviewResponse
from app.services.ai_router import ai_router
from app.services.groq_service import GroqServiceError
from app.services.project_context import project_context_builder, compute_paper_set_version

logger = logging.getLogger(__name__)
BATCH_SIZE = 10


class LiteratureReviewService:
    """Orchestrates the multi-stage literature review generation pipeline."""

    async def _analyze_papers_in_batches(self, paper_dicts: List[Dict]) -> List[Dict]:
        analyses = []
        for i in range(0, len(paper_dicts), BATCH_SIZE):
            batch = paper_dicts[i: i + BATCH_SIZE]
            logger.info("Analyzing batch %d/%d (%d papers)", i // BATCH_SIZE + 1,
                        (len(paper_dicts) + BATCH_SIZE - 1) // BATCH_SIZE, len(batch))
            tasks = [ai_router.analyze_paper_for_review(p) for p in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for j, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error("Paper analysis failed for %s: %s", batch[j].get("id"), result)
                    analyses.append({
                        "paper_id": str(batch[j].get("id", "")),
                        "title": batch[j].get("title", "Unknown"),
                        "year": batch[j].get("year"),
                        "authors": batch[j].get("authors", "N/A"),
                        "research_problem": None, "methodology": None,
                        "datasets": [], "models": [], "algorithms": [],
                        "metrics": [], "key_findings": [], "limitations": [],
                        "future_work": [], "contribution": None,
                    })
                else:
                    analyses.append(result)
        return analyses

    async def get_cached_review(self, session, project_id, user_id, current_paper_ids) -> Optional[LiteratureReviewResponse]:
        stmt = select(LiteratureReview).where(
            LiteratureReview.project_id == project_id,
            LiteratureReview.user_id == user_id,
        )
        review = await session.scalar(stmt)
        if not review:
            return None
        current_version = compute_paper_set_version(current_paper_ids)
        is_stale = review.paper_set_version != current_version or review.paper_count != len(current_paper_ids)
        try:
            content = LiteratureReviewContent(**review.content)
        except Exception as exc:
            logger.error("Failed to parse cached review: %s", exc)
            return None
        return LiteratureReviewResponse(
            id=str(review.id), project_id=str(project_id), content=content,
            paper_count=review.paper_count, is_stale=is_stale,
            created_at=review.created_at.isoformat(),
        )

    async def generate(self, session, project_id, user_id, force_regenerate=False) -> LiteratureReviewResponse:
        project, paper_dicts = await project_context_builder.get_all_paper_dicts(session, project_id, user_id)
        if project is None:
            raise ValueError("Project not found or access denied.")
        if not paper_dicts:
            raise ValueError("This project has no papers. Add papers before generating a literature review.")

        paper_ids = [p["id"] for p in paper_dicts]
        current_version = compute_paper_set_version(paper_ids)

        if not force_regenerate:
            cached = await self.get_cached_review(session, project_id, user_id, paper_ids)
            if cached and not cached.is_stale:
                logger.info("Returning cached review for project %s", project_id)
                return cached

        logger.info("Generating lit review for project %s (%d papers)", project_id, len(paper_dicts))

        analyses = await self._analyze_papers_in_batches(paper_dicts)
        content = await ai_router.synthesize_literature_review(analyses, project.name)

        stmt = select(LiteratureReview).where(
            LiteratureReview.project_id == project_id,
            LiteratureReview.user_id == user_id,
        )
        existing = await session.scalar(stmt)
        content_dict = content.model_dump()

        if existing:
            existing.paper_set_version = current_version
            existing.paper_count = len(paper_dicts)
            existing.content = content_dict
        else:
            session.add(LiteratureReview(
                project_id=project_id, user_id=user_id,
                paper_set_version=current_version, paper_count=len(paper_dicts),
                content=content_dict,
            ))

        await session.commit()

        stmt = select(LiteratureReview).where(
            LiteratureReview.project_id == project_id,
            LiteratureReview.user_id == user_id,
        )
        saved = await session.scalar(stmt)

        return LiteratureReviewResponse(
            id=str(saved.id) if saved else None,
            project_id=str(project_id),
            content=content,
            paper_count=len(paper_dicts),
            is_stale=False,
            created_at=saved.created_at.isoformat() if saved else None,
        )

    async def invalidate(self, session, project_id, user_id) -> bool:
        stmt = select(LiteratureReview).where(
            LiteratureReview.project_id == project_id,
            LiteratureReview.user_id == user_id,
        )
        review = await session.scalar(stmt)
        if not review:
            return False
        await session.delete(review)
        await session.commit()
        return True


literature_review_service = LiteratureReviewService()
'''

with open("app/services/literature_review_service.py", "w", encoding="utf-8") as f:
    f.write(LRS_CODE)

print("Both files written OK")

