"""
Concept graph extraction pipeline.

    paper + compiled source units
        ↓ concept + relation extraction (routed LLM, evidence required)
        ↓ canonicalization (alias-aware, conservative)
        ↓ provenance resolution (page + chunk_id per concept)
        ↓ idempotent Postgres write (replace this paper's rows, keep shared keys)

Two failures made the original version produce an empty graph in production:

1. It called Groq with a hardcoded ``llama3-70b-8192``, which Groq has
   decommissioned. Every extraction raised, the exception was swallowed by a
   broad ``except``, and the function returned having written nothing. Model
   choice now comes from the routing table like every other AI task.
2. It attached concepts with no provenance and no concept-to-concept edges, so
   even a successful run produced a star of unlabelled nodes around a paper
   rather than a graph.
"""

import logging
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KIND_CONCEPT, KIND_SOURCE, ConceptRelation, KnowledgeEntry, PaperConcept
from app.models.paper import Paper
from app.services.prompts import CONCEPT_RELATION_TYPES, build_concept_extraction_messages

logger = logging.getLogger(__name__)

#: Chunks pulled from Neo4j to ground extraction in real body text rather than
#: just the abstract.
MAX_CONTEXT_CHUNKS = 15

#: Concepts this generic are never useful as graph nodes — they connect
#: everything to everything and carry no information.
STOP_CONCEPTS = {
    "model", "models", "method", "methods", "approach", "approaches", "data",
    "dataset", "datasets", "result", "results", "experiment", "experiments",
    "paper", "papers", "study", "studies", "work", "system", "systems",
    "technique", "techniques", "algorithm", "algorithms", "task", "tasks",
    "problem", "problems", "analysis", "framework", "research", "performance",
    "accuracy", "value", "values", "number", "numbers", "example", "examples",
}

#: Suffix words dropped when they are pure padding on a technical term, so
#: "Self-Attention Mechanism" and "Self-Attention" canonicalize together.
_PADDING_SUFFIXES = (
    "mechanism", "mechanisms", "architecture", "architectures",
    "technique", "techniques", "approach", "approaches",
    "algorithm", "algorithms", "method", "methods", "model", "models",
    "layer", "layers", "module", "modules", "framework", "frameworks",
    "strategy", "strategies", "scheme", "schemes", "procedure", "procedures",
)

#: Determiners and fillers that must never survive as a concept on their own.
#: `canonical_key("the method")` drops the padding word "method" and would
#: otherwise leave the bare determiner "the" as a valid concept node.
_NON_CONCEPT_TOKENS = {
    "the", "a", "an", "this", "that", "these", "those", "its", "their",
    "our", "his", "her", "it", "we", "they", "such", "same", "other",
}

_IRREGULAR_PLURALS = {
    "analyses": "analysis", "hypotheses": "hypothesis", "matrices": "matrix",
    "indices": "index", "vertices": "vertex", "corpora": "corpus",
    "criteria": "criterion", "phenomena": "phenomenon", "series": "series",
}


# ── Canonicalization ──────────────────────────────────────────────────────────

def _singularize(word: str) -> str:
    """Conservative singularization.

    The original implementation stripped a trailing 's' from anything, which
    turned domain terms ending in 's' into non-words ("bias" -> "bia",
    "corpus" -> "corpu") and merged genuinely distinct concepts. This handles
    the irregular cases explicitly and refuses to touch short words or the
    -ss / -us / -is endings where a trailing 's' is part of the stem.
    """
    lower = word.lower()
    if lower in _IRREGULAR_PLURALS:
        return _IRREGULAR_PLURALS[lower]
    if len(lower) <= 3:
        return lower
    if lower.endswith(("ss", "us", "is", "as")):
        return lower
    if lower.endswith("ies") and len(lower) > 4:
        return lower[:-3] + "y"
    if lower.endswith("ses") or lower.endswith("xes") or lower.endswith("ches"):
        return lower[:-2]
    if lower.endswith("s"):
        return lower[:-1]
    return lower


def canonical_key(name: str) -> str:
    """Return the identity key two surface forms must share to be one concept.

    Folds case, punctuation and separator differences, drops a trailing padding
    word, and singularizes the final token. So these four collapse to one node:

        "self-attention"  "Self Attention"  "Self-Attention"  "Self-Attention Mechanism"

    It deliberately does not do stemming or synonym expansion: "Self-Attention"
    and "Cross-Attention" differ in a meaningful token and stay separate, which
    is the failure mode to avoid in the other direction.
    """
    if not name:
        return ""
    text = name.strip().lower()
    text = re.sub(r"[‐-―]", "-", text)      # unicode dashes -> hyphen
    text = re.sub(r"[^a-z0-9]+", " ", text)            # hyphens/underscores -> space
    tokens = [t for t in text.split() if t]
    if not tokens:
        return ""
    # Drop a trailing padding word only when something meaningful remains.
    if len(tokens) > 1 and tokens[-1] in _PADDING_SUFFIXES:
        tokens = tokens[:-1]
    if not tokens:
        return ""
    tokens[-1] = _singularize(tokens[-1])
    return " ".join(tokens)


def display_name(name: str) -> str:
    """Human-facing label: trimmed, whitespace-normalized, original casing kept.

    Casing from the paper is preserved because acronyms matter here — forcing
    Title Case would render "BERT" as "Bert" and "GPU" as "Gpu".
    """
    return re.sub(r"\s+", " ", (name or "").strip())


def concept_id_for(canonical: str) -> str:
    """Deterministic node ID, so the same concept is the same node everywhere."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"saira:concept:{canonical}"))


def is_valid_concept(name: str, canonical: str) -> bool:
    if not canonical or len(canonical) < 3:
        return False
    if canonical in STOP_CONCEPTS:
        return False
    # Reject a concept whose every token is a stopword ("the results", "a model")
    tokens = canonical.split()
    if all(t in STOP_CONCEPTS or t in _NON_CONCEPT_TOKENS for t in tokens):
        return False
    if len(tokens) > 8:            # a sentence, not a concept
        return False
    if not re.search(r"[a-z]", canonical):
        return False
    return True


# ── Service ───────────────────────────────────────────────────────────────────

class ConceptService:

    async def _load_chunks(
        self, db_session: AsyncSession, paper_id: str
    ) -> List[Dict[str, Any]]:
        """Fetch this paper's verbatim source units for grounding.

        Reads `knowledge_entries` rather than Neo4j chunks after the LLM-Wiki
        migration. The dict shape (`id`/`text`/`page`) is unchanged so the
        evidence-location logic below did not have to move.
        """
        try:
            rows = await db_session.execute(
                select(
                    KnowledgeEntry.entry_key,
                    KnowledgeEntry.body,
                    KnowledgeEntry.page,
                )
                .where(
                    KnowledgeEntry.paper_id == uuid.UUID(str(paper_id)),
                    KnowledgeEntry.kind == KIND_SOURCE,
                )
                .order_by(KnowledgeEntry.ordinal)
                .limit(MAX_CONTEXT_CHUNKS)
            )
            return [{"id": r[0], "text": r[1], "page": r[2]} for r in rows]
        except Exception as exc:
            logger.warning("Could not fetch source units for concept extraction: %s", exc)
            return []

    def _locate_evidence(
        self, evidence: str, chunks: List[Dict[str, Any]]
    ) -> Tuple[List[int], List[str]]:
        """Map an evidence quote back to the chunk(s) and page(s) it came from.

        This is what gives a concept real provenance instead of a bare link to
        the paper. Matching is done on a normalized substring so minor
        whitespace/quote differences in the model's copy still resolve; if
        nothing matches, the concept keeps empty provenance rather than being
        assigned a fabricated page.
        """
        if not evidence or not chunks:
            return [], []
        needle = re.sub(r"\s+", " ", evidence.lower()).strip()
        if len(needle) < 12:
            return [], []
        # Use a middle slice so leading/trailing ellipses in the quote don't break the match.
        probe = needle[: min(len(needle), 60)]
        pages: List[int] = []
        chunk_ids: List[str] = []
        for ch in chunks:
            hay = re.sub(r"\s+", " ", (ch.get("text") or "").lower())
            if probe and probe in hay:
                if ch.get("page") is not None and ch["page"] not in pages:
                    pages.append(ch["page"])
                if ch.get("id") and ch["id"] not in chunk_ids:
                    chunk_ids.append(ch["id"])
        return pages, chunk_ids

    async def extract_concepts(
        self, paper_dict: Dict[str, Any], chunks: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Call the routed model and return raw {concepts, relations}."""
        from app.services.ai_router import concept_extraction_model
        from app.services.groq_service import groq_service

        if chunks:
            paper_dict = dict(paper_dict)
            paper_dict["full_text_sample"] = "\n...\n".join(
                (c.get("text") or "")[:1500] for c in chunks
            )

        messages = build_concept_extraction_messages(paper_dict)
        return await groq_service.chat_complete_json(
            model=concept_extraction_model(),
            messages=messages,
            temperature=0.1,
        )

    def normalize_payload(
        self, raw: Dict[str, Any], chunks: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, int]]:
        """Canonicalize concepts, resolve provenance, and validate relations.

        Returns (concepts, relations, stats). Relations whose endpoints did not
        survive concept validation are dropped rather than pointed at a node
        that does not exist — a dangling edge would render as a phantom node in
        the graph UI.
        """
        stats = {
            "raw_concepts": 0, "rejected_generic": 0, "merged_duplicates": 0,
            "raw_relations": 0, "rejected_relations": 0, "with_provenance": 0,
        }

        by_key: Dict[str, Dict[str, Any]] = {}
        name_to_key: Dict[str, str] = {}

        for item in (raw.get("concepts") or []):
            if not isinstance(item, dict):
                continue
            stats["raw_concepts"] += 1
            surface = display_name(str(item.get("name") or ""))
            key = canonical_key(surface)
            if not is_valid_concept(surface, key):
                stats["rejected_generic"] += 1
                continue

            try:
                importance = float(item.get("importance", 0.5))
            except (TypeError, ValueError):
                importance = 0.5
            importance = min(max(importance, 0.0), 1.0)

            evidence = str(item.get("evidence") or "").strip()[:600]
            pages, chunk_ids = self._locate_evidence(evidence, chunks)

            name_to_key[surface.lower()] = key
            existing = by_key.get(key)
            if existing:
                # Same concept, different surface form — keep one node, record
                # the variant as an alias instead of creating a second node.
                stats["merged_duplicates"] += 1
                if surface not in existing["aliases"]:
                    existing["aliases"].append(surface)
                existing["importance"] = max(existing["importance"], importance)
                existing["pages"] = sorted(set(existing["pages"]) | set(pages))
                existing["chunk_ids"] = sorted(set(existing["chunk_ids"]) | set(chunk_ids))
                if not existing["evidence"] and evidence:
                    existing["evidence"] = evidence
                continue

            by_key[key] = {
                "id": concept_id_for(key),
                "name": surface,
                "canonical": key,
                "aliases": [surface],
                "importance": importance,
                "evidence": evidence,
                "pages": pages,
                "chunk_ids": chunk_ids,
            }

        for c in by_key.values():
            if c["chunk_ids"]:
                stats["with_provenance"] += 1

        allowed_types = set(CONCEPT_RELATION_TYPES)
        relations: List[Dict[str, Any]] = []
        seen_rel = set()
        for item in (raw.get("relations") or []):
            if not isinstance(item, dict):
                continue
            stats["raw_relations"] += 1
            rtype = str(item.get("type") or "").strip().upper().replace(" ", "_")
            src_key = canonical_key(str(item.get("source") or ""))
            tgt_key = canonical_key(str(item.get("target") or ""))

            if rtype not in allowed_types or not src_key or not tgt_key:
                stats["rejected_relations"] += 1
                continue
            if src_key == tgt_key:                       # self-loop carries nothing
                stats["rejected_relations"] += 1
                continue
            if src_key not in by_key or tgt_key not in by_key:
                stats["rejected_relations"] += 1
                continue

            dedupe = (src_key, tgt_key, rtype)
            if dedupe in seen_rel:
                continue
            seen_rel.add(dedupe)

            evidence = str(item.get("evidence") or "").strip()[:600]
            pages, chunk_ids = self._locate_evidence(evidence, chunks)
            relations.append({
                "source_key": src_key,
                "target_key": tgt_key,
                "source_id": by_key[src_key]["id"],
                "target_id": by_key[tgt_key]["id"],
                "type": rtype,
                "evidence": evidence,
                "pages": pages,
                "chunk_ids": chunk_ids,
            })

        # Strip the working field before it reaches Cypher.
        concepts = []
        for c in by_key.values():
            # `canonical` is retained deliberately: it is `concept_key` in
            # Postgres, the value that makes two papers' mentions of the same
            # concept the same concept. The Neo4j writer used to drop it
            # because the node id carried identity instead.
            concepts.append(dict(c))

        return concepts, relations, stats

    async def sync_paper_concepts(
        self, db_session: AsyncSession, paper_id: str, replace: bool = True
    ) -> Dict[str, Any]:
        """Extract and persist this paper's concept subgraph.

        `replace=True` (the default) makes re-ingestion idempotent: this
        paper's existing HAS_CONCEPT edges and its own RELATES_TO assertions
        are deleted before the new ones are written, so ingesting the same
        paper twice leaves the graph the same size rather than doubling it.
        Shared Concept nodes are never deleted here — other papers may still
        reference them.
        """
        report: Dict[str, Any] = {
            "paper_id": paper_id, "ok": False, "concepts": 0,
            "relations": 0, "error": None, "stats": {},
        }

        paper = await db_session.scalar(select(Paper).where(Paper.id == uuid.UUID(paper_id)))
        if not paper:
            report["error"] = "paper_not_found"
            logger.error("Cannot sync concepts: Paper %s not found in DB.", paper_id)
            return report

        paper_dict = {
            "id": str(paper.id),
            "title": paper.title,
            "abstract": paper.abstract,
            "publication_year": paper.publication_year,
            "venue": paper.venue,
        }

        chunks = await self._load_chunks(db_session, paper_id)
        if not chunks:
            logger.info("Paper %s has no compiled source units; extracting from metadata only.", paper_id)

        try:
            raw = await self.extract_concepts(paper_dict, chunks)
        except Exception as exc:
            report["error"] = f"extraction_failed: {exc}"
            logger.error("Concept extraction failed for %s: %s", paper_id, exc)
            return report

        concepts, relations, stats = self.normalize_payload(raw, chunks)
        report["stats"] = stats

        if not concepts:
            report["error"] = "no_valid_concepts"
            logger.info("No valid concepts extracted for Paper %s (stats=%s).", paper_id, stats)
            return report

        try:
            pid = uuid.UUID(str(paper_id))
            if replace:
                # Replace this paper's assertions only. `concept_key` is shared
                # across papers by design — deleting rows here never removes
                # another paper's view of the same concept, which is what the
                # Neo4j version achieved by keeping shared :Concept nodes and
                # dropping only this paper's edges. Orphan pruning is no longer
                # needed: with no standalone concept node to strand, a concept
                # simply stops appearing once no paper asserts it.
                await db_session.execute(
                    delete(PaperConcept).where(PaperConcept.paper_id == pid)
                )
                await db_session.execute(
                    delete(ConceptRelation).where(ConceptRelation.paper_id == pid)
                )
                await db_session.execute(
                    delete(KnowledgeEntry).where(
                        KnowledgeEntry.paper_id == pid,
                        KnowledgeEntry.kind == KIND_CONCEPT,
                    )
                )

            from app.services.knowledge_compiler import slugify

            base_ordinal = 900_000  # well past any source/compiled ordinal
            for offset, c in enumerate(concepts):
                key = c.get("canonical") or c["id"]
                db_session.add(PaperConcept(
                    paper_id=pid,
                    concept_key=key,
                    name=c.get("name") or key,
                    kind=KIND_CONCEPT,
                    description=c.get("description") or None,
                    evidence=c.get("evidence") or None,
                    pages=c.get("pages") or [],
                    entry_keys=c.get("chunk_ids") or [],
                ))
                db_session.add(KnowledgeEntry(
                    paper_id=pid,
                    entry_key=f"{paper_id}::concept::{slugify(key)}",
                    kind=KIND_CONCEPT,
                    slug=slugify(key),
                    title=c.get("name") or key,
                    section="Key Concepts",
                    body=c.get("description") or c.get("name") or key,
                    page=(c.get("pages") or [None])[0],
                    ordinal=base_ordinal + offset,
                    provenance={
                        "pages": c.get("pages") or [],
                        "source_text": c.get("evidence") or "",
                        "evidence_keys": c.get("chunk_ids") or [],
                        "verified": bool(c.get("chunk_ids")),
                    },
                ))

            seen_edges = set()
            for r in relations:
                edge = (r["source_key"], r["target_key"], r.get("type") or "RELATES_TO")
                if edge in seen_edges:
                    continue
                seen_edges.add(edge)
                db_session.add(ConceptRelation(
                    paper_id=pid,
                    source_key=r["source_key"],
                    target_key=r["target_key"],
                    relation_type=r.get("type") or "RELATES_TO",
                ))

            await db_session.commit()
        except Exception as exc:
            await db_session.rollback()
            report["error"] = f"concept_write_failed: {exc}"
            logger.error("Failed to persist concepts for %s: %s", paper_id, exc)
            return report

        report.update(ok=True, concepts=len(concepts), relations=len(relations))
        logger.info(
            "Synced %d concepts / %d relations for Paper %s (stats=%s)",
            len(concepts), len(relations), paper_id, stats,
        )
        return report


concept_service = ConceptService()
