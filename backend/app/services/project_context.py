import hashlib
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


def _first_summary(paper) -> Optional[str]:
    """Best available cached summary for a paper, or None.

    `Paper.analysis` is a list (it comes from a backref), and PaperAnalysis has
    no `summary_tldr` column — it has summary_eli5/_student/_researcher. The
    previous `paper.analysis.summary_tldr` expression only avoided raising
    because the table was empty; it would have crashed on the first analysed
    paper.
    """
    analyses = getattr(paper, "analysis", None) or []
    if not isinstance(analyses, (list, tuple)):
        analyses = [analyses]
    for a in analyses:
        for field in ("summary_researcher", "summary_student", "summary_eli5"):
            value = getattr(a, field, None)
            if value:
                return value
    return None


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
            "summary_tldr": _first_summary(paper),
            "notes": [n.content for n in (pp.notes or [])],
            "highlights": [h.selected_text + (f" (Note: {h.ai_note})" if getattr(h, "ai_note", None) else "") for h in (pp.highlights or [])],
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
                summary = _first_summary(paper)
                if summary:
                    lines.append(f"Summary: {summary}")
                elif paper.abstract:
                    lines.append(f"Abstract: {paper.abstract[:300]}")
                for n in (pp.notes or []):
                    lines.append(f"User Note: {n.content}")
                for h in (pp.highlights or []):
                    lines.append(f"Highlight: {h.selected_text}" + (f" (Note: {h.ai_note})" if getattr(h, "ai_note", None) else ""))
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
