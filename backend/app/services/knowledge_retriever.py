"""
Knowledge retrieval over the compiled wiki.

The old architecture embedded every chunk with a local MiniLM and ranked with
a brute-force cosine scan in Neo4j. This ranks with PostgreSQL full-text
search over `knowledge_entries.search_vector` — no embedding model, no vector
store, no second database.

Two properties of the old design are deliberately preserved, because they were
the parts that made it correct rather than the parts that made it expensive:

1. **Scope first.** The paper-id restriction is applied in the WHERE clause,
   before ranking, so top-k is computed *within* the caller's scope. Ranking
   globally and filtering afterwards would silently return fewer than k
   in-scope results — a recall bug and a leak risk in one.
2. **The scope is server-resolved.** This module never accepts a scope from a
   request body. It takes an explicit list of paper IDs that
   `retrieval_service` produced from the database using the caller's user_id.

Ranking is `ts_rank_cd` with the `32` normalization flag, which maps to
`rank/(rank+1)` and therefore lands in `[0, 1)` — the same shape cosine
similarity had, so score thresholds and debug output downstream still read the
way they did.

ponytail: keyword search first, exactly as the migration brief asks. No
embeddings, no reranker, no hybrid fusion. The interface below is the seam to
add semantic search behind if evaluation ever shows keyword recall is not
enough — see `search()`.
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import (
    KIND_COMPILED,
    KIND_CONCEPT,
    KIND_METHOD,
    KIND_SOURCE,
    KIND_TOPIC,
)

logger = logging.getLogger(__name__)

#: Relative weight per entry kind. Verbatim source text outranks compiled prose
#: at equal textual relevance, so a citation prefers the paper's own words.
_KIND_WEIGHTS: Dict[str, float] = {
    KIND_SOURCE: 1.0,
    KIND_COMPILED: 0.95,
    KIND_CONCEPT: 0.85,
    KIND_METHOD: 0.85,
    KIND_TOPIC: 0.75,
}

#: Dropped before building the tsquery. Postgres would stem them away anyway,
#: but removing them here keeps the OR-query short and the `ILIKE` fallback
#: from matching on "the".
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "can", "did", "do",
    "does", "for", "from", "had", "has", "have", "how", "in", "into", "is", "it",
    "its", "of", "on", "or", "that", "the", "their", "them", "then", "there",
    "these", "they", "this", "to", "was", "were", "what", "when", "where",
    "which", "who", "why", "will", "with", "would", "you", "your", "about",
    "explain", "describe", "tell", "me", "give", "list", "does", "using", "use",
    "paper", "papers", "study", "please",
}

#: Section weight. Back matter is real text a user may legitimately ask about,
#: so it stays searchable — but it must not outrank the paper's own argument.
#: The first end-to-end run had a bibliography entry ranked first for both
#: "what method does this evaluate?" and "how was it evaluated?", because
#: reference lists are unusually dense in exactly the terms a question uses.
_SECTION_WEIGHTS: Dict[str, float] = {
    "References": 0.25,
    "Acknowledgements": 0.3,
    "Appendix": 0.7,
}


def _section_weight(section: Optional[str]) -> float:
    return _SECTION_WEIGHTS.get(section or "", 1.0)


_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9+#._-]*")

#: More terms than this and the OR-query stops adding recall and starts adding
#: latency.
_MAX_TERMS = 24


@dataclass
class KnowledgeHit:
    """One retrieved knowledge entry with everything a citation needs."""

    entry_key: str
    paper_id: str
    kind: str
    title: Optional[str]
    section: Optional[str]
    body: str
    page: Optional[int]
    ordinal: Optional[int]
    score: float
    paper_title: Optional[str]
    provenance: Optional[Dict[str, Any]]

    @property
    def verified(self) -> bool:
        """Source text is verbatim, so always verified. Compiled entries are
        verified only if their evidence quote was located in the source."""
        if self.kind == KIND_SOURCE:
            return True
        return bool((self.provenance or {}).get("verified"))


def build_terms(query: str) -> List[str]:
    """Reduce a natural-language question to searchable terms."""
    terms: List[str] = []
    for match in _WORD.finditer(query or ""):
        word = match.group(0).lower().strip("._-")
        if len(word) < 3 or word in _STOPWORDS:
            continue
        if word not in terms:
            terms.append(word)
        if len(terms) >= _MAX_TERMS:
            break
    return terms


#: Question intent → section names worth matching. Section headings sit at
#: weight B in the tsvector, so adding one to the query pulls in that whole
#: section of every in-scope paper.
#:
#: This exists because of a real failure found in end-to-end testing: "What
#: problem does this paper solve?" retrieved NOTHING. Every content word in it
#: is either a stopword or absent from the paper's own vocabulary — papers
#: state their problem, they do not use the word "problem". Pure keyword
#: retrieval cannot bridge that on its own, and it is the case people ask
#: first. Mapping intent onto the section metadata the compiler already
#: produces is far cheaper than reintroducing an embedding model, and it fails
#: safe: at worst the reader gets the Introduction.
_INTENT_SECTIONS: Dict[str, tuple[str, ...]] = {
    "problem": ("Introduction", "Abstract"),
    "solve": ("Introduction", "Abstract"),
    "solves": ("Introduction", "Abstract"),
    "motivation": ("Introduction",),
    "about": ("Abstract", "Introduction"),
    "summary": ("Abstract", "Conclusion"),
    "summarize": ("Abstract", "Conclusion"),
    "contribution": ("Introduction", "Abstract"),
    "contributions": ("Introduction", "Abstract"),
    "method": ("Methodology",),
    "methods": ("Methodology",),
    "methodology": ("Methodology",),
    "approach": ("Methodology",),
    "technique": ("Methodology",),
    "architecture": ("Methodology",),
    "work": ("Methodology",),
    "works": ("Methodology",),
    "dataset": ("Dataset", "Experiments"),
    "datasets": ("Dataset", "Experiments"),
    "data": ("Dataset", "Experiments"),
    "corpus": ("Dataset",),
    "benchmark": ("Dataset", "Experiments"),
    "experiment": ("Experiments",),
    "experiments": ("Experiments",),
    "evaluate": ("Experiments", "Results"),
    "evaluated": ("Experiments", "Results"),
    "evaluation": ("Experiments", "Results"),
    "result": ("Results",),
    "results": ("Results",),
    "finding": ("Results",),
    "findings": ("Results",),
    "performance": ("Results",),
    "accuracy": ("Results",),
    "outcome": ("Results",),
    "limitation": ("Limitations", "Discussion", "Conclusion"),
    "limitations": ("Limitations", "Discussion", "Conclusion"),
    "weakness": ("Limitations", "Discussion"),
    "drawback": ("Limitations", "Discussion"),
    "future": ("Conclusion",),
    "conclusion": ("Conclusion",),
    "conclude": ("Conclusion",),
}

#: Below this many content terms, a question is generic enough that section
#: expansion is the difference between an answer and an abstention. Above it,
#: the question carries its own vocabulary and expansion would only add noise.
_EXPAND_BELOW_TERMS = 5


def expand_with_sections(query: str, terms: Sequence[str]) -> List[str]:
    """Add section names implied by the question's intent.

    Applied only to short/generic questions — a question with enough of its own
    content words ranks better without the extra noise.
    """
    if len(terms) >= _EXPAND_BELOW_TERMS:
        return list(terms)

    lowered = (query or "").lower()
    extra: List[str] = []
    for word, sections in _INTENT_SECTIONS.items():
        if re.search(rf"\b{re.escape(word)}\b", lowered):
            for section in sections:
                for piece in section.lower().split():
                    if piece not in terms and piece not in extra:
                        extra.append(piece)
    return list(terms) + extra


def build_tsquery(terms: Sequence[str]) -> str:
    """OR the terms together.

    `websearch_to_tsquery` would AND them, which returns nothing for any
    question longer than a few words — the failure mode that makes people
    conclude keyword search "doesn't work" for RAG. OR plus `ts_rank_cd`
    (which rewards density and proximity of matches) gives recall on long
    questions while still ranking the on-topic entries first.
    """
    safe = [re.sub(r"[^A-Za-z0-9+#._-]", "", t) for t in terms]
    return " | ".join(t for t in safe if t)


class KnowledgeRetriever(ABC):
    """The retrieval seam. Nothing above this depends on Postgres FTS."""

    @abstractmethod
    async def search(
        self,
        db: AsyncSession,
        query: str,
        paper_ids: Sequence[str],
        top_k: int = 10,
        kinds: Optional[Sequence[str]] = None,
    ) -> List[KnowledgeHit]:
        """Rank knowledge entries restricted to `paper_ids`."""

    async def search_paper(
        self,
        db: AsyncSession,
        query: str,
        paper_id: str,
        top_k: int = 5,
        kinds: Optional[Sequence[str]] = None,
    ) -> List[KnowledgeHit]:
        """Paper Chat. A single-paper scope, enforced by construction — the
        list passed downstream contains exactly one ID."""
        return await self.search(db, query, [str(paper_id)], top_k=top_k, kinds=kinds)

    async def search_project(
        self,
        db: AsyncSession,
        query: str,
        paper_ids: Sequence[str],
        top_k: int = 10,
        kinds: Optional[Sequence[str]] = None,
    ) -> List[KnowledgeHit]:
        """Project Chat. Spans every paper in the project and nothing else."""
        return await self.search(db, query, paper_ids, top_k=top_k, kinds=kinds)


class PostgresKnowledgeRetriever(KnowledgeRetriever):

    _SELECT = """
        SELECT ke.entry_key,
               ke.paper_id::text  AS paper_id,
               ke.kind,
               ke.title,
               ke.section,
               ke.body,
               ke.page,
               ke.ordinal,
               ke.provenance,
               p.title            AS paper_title,
               ts_rank_cd(ke.search_vector, q.query, 32) AS rank
        FROM knowledge_entries ke
        JOIN papers p ON p.id = ke.paper_id,
             to_tsquery('english', :tsquery) AS q(query)
        WHERE ke.paper_id = ANY(CAST(:paper_ids AS uuid[]))
          AND ke.search_vector @@ q.query
          {kind_clause}
        ORDER BY rank DESC
        LIMIT :limit
    """

    # Substring fallback. Runs only when the ranked query found nothing at all,
    # which happens for questions made entirely of terms the corpus does not
    # contain in stemmed form (identifiers, rare acronyms, misspellings).
    _FALLBACK = """
        SELECT ke.entry_key,
               ke.paper_id::text  AS paper_id,
               ke.kind,
               ke.title,
               ke.section,
               ke.body,
               ke.page,
               ke.ordinal,
               ke.provenance,
               p.title            AS paper_title,
               0.01               AS rank
        FROM knowledge_entries ke
        JOIN papers p ON p.id = ke.paper_id
        WHERE ke.paper_id = ANY(CAST(:paper_ids AS uuid[]))
          AND ke.body ILIKE :needle
          {kind_clause}
        ORDER BY ke.kind = 'source' DESC, ke.ordinal ASC
        LIMIT :limit
    """

    async def search(
        self,
        db: AsyncSession,
        query: str,
        paper_ids: Sequence[str],
        top_k: int = 10,
        kinds: Optional[Sequence[str]] = None,
    ) -> List[KnowledgeHit]:
        ids = [str(p) for p in paper_ids if p]
        if not ids or not (query or "").strip():
            return []

        kind_clause = ""
        params: Dict[str, Any] = {
            "paper_ids": ids,
            # Over-fetch, then re-rank by kind weight and trim. Applying the
            # weight in SQL would mean ranking on an expression Postgres cannot
            # use the GIN index for.
            "limit": max(top_k * 3, top_k),
        }
        if kinds:
            kind_clause = "AND ke.kind = ANY(:kinds)"
            params["kinds"] = list(kinds)

        terms = build_terms(query)
        rows: List[Any] = []
        if terms:
            params["tsquery"] = build_tsquery(expand_with_sections(query, terms))
            stmt = text(self._SELECT.format(kind_clause=kind_clause))
            try:
                result = await db.execute(stmt, params)
                rows = list(result.mappings())
            except Exception as exc:
                # Retrieval never raises: an empty result degrades to "no
                # evidence" and the grounding policy makes the model abstain,
                # which is safer than a 500 and much safer than an ungrounded
                # answer.
                logger.warning("knowledge_search_failed query=%r error=%s", query[:80], exc)
                return []

        if not rows and terms:
            longest = max(terms, key=len)
            fb_params = dict(params)
            fb_params.pop("tsquery", None)
            fb_params["needle"] = f"%{longest}%"
            try:
                result = await db.execute(
                    text(self._FALLBACK.format(kind_clause=kind_clause)), fb_params
                )
                rows = list(result.mappings())
                if rows:
                    logger.info(
                        "knowledge_search_fallback term=%r hits=%d", longest, len(rows)
                    )
            except Exception as exc:
                logger.warning("knowledge_search_fallback_failed error=%s", exc)
                return []

        hits = [
            KnowledgeHit(
                entry_key=r["entry_key"],
                paper_id=r["paper_id"],
                kind=r["kind"],
                title=r["title"],
                section=r["section"],
                body=r["body"] or "",
                page=r["page"],
                ordinal=r["ordinal"],
                score=(
                    float(r["rank"] or 0.0)
                    * _KIND_WEIGHTS.get(r["kind"], 0.8)
                    * _section_weight(r["section"])
                ),
                paper_title=r["paper_title"],
                provenance=r["provenance"],
            )
            for r in rows
        ]
        hits.sort(key=lambda h: h.score, reverse=True)

        allowed = set(ids)
        safe: List[KnowledgeHit] = []
        for h in hits:
            # Defence in depth. The SQL already restricts to the scope; an
            # entry outside it is dropped here rather than reaching the model.
            if h.paper_id not in allowed:
                logger.error(
                    "Scope violation dropped: entry %s (paper %s) outside scope",
                    h.entry_key, h.paper_id,
                )
                continue
            safe.append(h)

        return safe[:top_k]


knowledge_retriever: KnowledgeRetriever = PostgresKnowledgeRetriever()
