"""
Knowledge compilation: PDF → source units → LLM-Wiki page.

This replaces the GraphRAG ingestion tail (chunk → embed → Neo4j) with a
compilation step that produces something a human can read and a retriever can
search without a vector index.

    PDF bytes
      ↓  text extraction            (PyMuPDF, per page — unchanged)
      ↓  normalization
      ↓  section detection          (new: headings become first-class metadata)
      ↓  bounded source units       (verbatim text, page + section preserved)
      ↓  LLM compilation            (one call, evidence quote required per field)
      ↓  evidence location          (each quote mapped back to a source unit)
      ↓  Markdown knowledge page    (knowledge store)
      ↓  index rows                 (Postgres, full-text searchable)

The grounding contract is the reason this is not a summarizer. Every compiled
field must carry a verbatim quote; the quote is located in the real source
text before the field is stored. A field whose quote cannot be found is kept
but marked `verified: false`, and the retriever will not offer it as primary
evidence. That is what stops a compilation error becoming a confident
fabrication downstream.

ponytail: heading detection is a heuristic over line shape, not a trained
layout model. It degrades to "one section called Body" on a PDF it cannot
parse, which still retrieves fine — the section label is a ranking and
citation nicety, not a correctness requirement.
"""

from __future__ import annotations

import logging
import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.knowledge import (
    KIND_COMPILED,
    KIND_CONCEPT,
    KIND_METHOD,
    KIND_SOURCE,
    KIND_TOPIC,
    ConceptRelation,
    KnowledgeEntry,
    PaperConcept,
)
from app.models.paper import Paper
from app.services.knowledge_store import knowledge_store, paper_page_path
from app.services.llm_provider import LLMError, llm_provider
from app.services.prompts import (
    KNOWLEDGE_SECTIONS,
    build_knowledge_compilation_messages,
)

logger = logging.getLogger(__name__)

#: Words per source unit, and the overlap between consecutive units. Kept close
#: to the old chunker's 500/50 so evidence granularity does not regress.
_UNIT_WORDS = 400
_UNIT_OVERLAP = 50

#: Sections the compiler prefers to send, most informative first. Taking the
#: head of the document instead spends the whole budget on the abstract and
#: introduction and never reaches results or limitations — and on an 8,000 TPM
#: provider budget there is no room to send everything. Section metadata is
#: what makes a better choice possible, so this is where it earns its keep.
_COMPILE_SECTION_PRIORITY = (
    "Abstract",
    "Introduction",
    "Methodology",
    "Results",
    "Dataset",
    "Conclusion",
    "Limitations",
    "Experiments",
    "Discussion",
    "Related Work",
    "Body",
)

#: Never worth the budget: back matter carries no compilable claim.
_COMPILE_SKIP_SECTIONS = {"References", "Acknowledgements", "Appendix"}

#: Evidence quotes shorter than this are too generic to locate meaningfully.
_MIN_EVIDENCE_CHARS = 24

#: Canonical section names. A detected heading is mapped onto one of these when
#: it is recognisable, so "3. Proposed Method" and "Methodology" rank together.
_CANONICAL_SECTIONS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"\babstract\b", re.I), "Abstract"),
    (re.compile(r"\bintroduction\b|\bbackground\b", re.I), "Introduction"),
    (re.compile(r"\brelated\s+work\b|\bprior\s+work\b|\bliterature\b", re.I), "Related Work"),
    (re.compile(r"\bmethod|\bapproach\b|\bmodel\b|\barchitecture\b|\bframework\b", re.I), "Methodology"),
    (re.compile(r"\bdata\s*set|\bdataset|\bcorpus\b|\bdata\b", re.I), "Dataset"),
    (re.compile(r"\bexperiment|\bsetup\b|\bimplementation\b|\bevaluation\b", re.I), "Experiments"),
    (re.compile(r"\bresult|\bfinding|\bperformance\b|\bablation\b", re.I), "Results"),
    (re.compile(r"\bdiscussion\b|\banalysis\b", re.I), "Discussion"),
    (re.compile(r"\blimitation|\bthreats?\s+to\s+validity\b", re.I), "Limitations"),
    (re.compile(r"\bconclusion|\bfuture\s+work\b|\bsummary\b", re.I), "Conclusion"),
    (re.compile(r"\breferences?\b|\bbibliography\b", re.I), "References"),
    (re.compile(r"\backnowledg", re.I), "Acknowledgements"),
    (re.compile(r"\bappendix\b|\bsupplement", re.I), "Appendix"),
]

#: A numbered heading ("3", "3.1", "IV.") followed by a short title.
_NUMBERED_HEADING = re.compile(r"^\s*(\d+(?:\.\d+)*|[IVXLC]+)[.)]?\s+(\S.{0,70})$")


class CompilationError(Exception):
    """Raised when a paper cannot be compiled into a knowledge page."""


@dataclass
class SourceUnit:
    """One bounded, verbatim piece of the paper. The only citable evidence.

    `paper_id` is filled in by the compiler once the owning paper is known, so
    extraction stays a pure function of the PDF and can be tested without a
    database.
    """

    ordinal: int
    text: str
    page: Optional[int]
    section: str
    paper_id: str = ""

    @property
    def normalized(self) -> str:
        return _normalize(self.text)


@dataclass
class CompiledField:
    key: str
    heading: str
    text: str
    evidence: str
    pages: List[int] = field(default_factory=list)
    entry_keys: List[str] = field(default_factory=list)

    @property
    def verified(self) -> bool:
        """True when the evidence quote was found in the paper's own text."""
        return bool(self.entry_keys)


@dataclass
class CompilationResult:
    paper_id: str
    source_units: int
    compiled_fields: int
    verified_fields: int
    concepts: int
    methods: int
    topics: int
    page_path: Optional[str] = None
    degraded: bool = False
    notes: List[str] = field(default_factory=list)

    def to_log(self) -> Dict[str, Any]:
        return {
            "paper_id": self.paper_id,
            "source_units": self.source_units,
            "compiled_fields": self.compiled_fields,
            "verified_fields": self.verified_fields,
            "concepts": self.concepts,
            "methods": self.methods,
            "topics": self.topics,
            "degraded": self.degraded,
            "notes": self.notes,
        }


# ── Text handling ─────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """Fold whitespace and unicode so an evidence quote can be matched against
    the source despite PDF line breaks, ligatures and curly quotes."""
    text = unicodedata.normalize("NFKD", text)
    text = text.replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')
    text = text.replace("–", "-").replace("—", "-")
    # Rejoin words hyphenated across a line break: "atten-\ntion" → "attention".
    text = re.sub(r"-\s*\n\s*", "", text)
    return re.sub(r"\s+", " ", text).strip().lower()


#: Markers of bibliography text. Reference lists are dense with technical
#: terms, so they match almost any query — the first end-to-end run had a
#: bibliography entry outranking real content on every question. They are
#: detected by content rather than by heading, because the "References"
#: heading is frequently missed on a two-column layout.
_REFERENCE_MARKERS = (
    re.compile(r"\bet al\.", re.I),
    re.compile(r"\bin proceedings\b|\bproc\.|\bconference on\b", re.I),
    re.compile(r"\barxiv\s*:?\s*\d{4}\.\d{4,5}", re.I),
    re.compile(r"\bpages?\s+\d+\s*[-–]\s*\d+", re.I),
    re.compile(r"\bdoi\s*:", re.I),
    re.compile(r"\(\s*(19|20)\d{2}\s*\)"),
)


def looks_like_references(text: str) -> bool:
    """True when a unit reads as bibliography rather than prose.

    Counts marker *occurrences* rather than distinct patterns. A body
    paragraph citing "Smith et al. (2023)" trips two patterns once each; a
    reference list trips them a dozen times. Thresholding on distinct patterns
    conflated the two and down-ranked real prose as back matter.
    """
    occurrences = sum(len(pattern.findall(text)) for pattern in _REFERENCE_MARKERS)
    if occurrences >= 5:
        return True
    # A dense run of "Name, A. B." author initials is the other strong signal.
    initials = len(re.findall(r"\b[A-Z]\.\s*[A-Z]?\.?,", text))
    return occurrences >= 3 and initials >= 3


def _looks_like_heading(line: str) -> bool:
    stripped = line.strip()
    if not (3 <= len(stripped) <= 90):
        return False
    # Formula fragments, table cells and truncated captions are not headings.
    # "AR = 1" and "Do not use phrases that 'provided con-" both slipped
    # through the first version and became section labels.
    if any(ch in stripped for ch in "=|"):
        return False
    if stripped.endswith("-"):
        return False
    if stripped[:1].islower():
        return False
    if stripped.endswith((".", ",", ";", ":")) and not _NUMBERED_HEADING.match(stripped):
        return False
    # A heading rarely contains sentence punctuation mid-line.
    if stripped.count(".") > 2:
        return False
    numbered = _NUMBERED_HEADING.match(stripped)
    if numbered:
        title = numbered.group(2).strip()
        if any(p.search(title) for p, _ in _CANONICAL_SECTIONS):
            return True
        # "1. Improving language models by retrieving from" is a reference
        # entry; "3.1 Experimental Setup" is a heading. Length separates them.
        return len(title.split()) <= 5
    words = stripped.split()
    if len(words) > 10:
        return False
    if stripped.isupper() and len(words) <= 8:
        return True
    for pattern, _ in _CANONICAL_SECTIONS:
        if pattern.search(stripped) and len(words) <= 6:
            return True
    return False


def _canonical_section(heading: str) -> str:
    for pattern, canonical in _CANONICAL_SECTIONS:
        if pattern.search(heading):
            return canonical
    cleaned = _NUMBERED_HEADING.match(heading.strip())
    if cleaned:
        return cleaned.group(2).strip()[:120]
    return heading.strip()[:120] or "Body"


def _split_words(text: str) -> List[str]:
    return text.split()


def extract_source_units(pdf_bytes: bytes) -> List[SourceUnit]:
    """Extract page text, detect sections, and emit bounded verbatim units.

    Raises CompilationError when the PDF yields no usable text — a scanned
    image, an encrypted file, or an HTML page that slipped past validation.
    """
    try:
        import pymupdf
    except ImportError:  # pragma: no cover - older PyMuPDF only exposes `fitz`
        try:
            import fitz as pymupdf  # type: ignore
        except ImportError as exc:
            raise CompilationError("PyMuPDF is not installed") from exc

    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise CompilationError(f"Could not open PDF: {exc}") from exc

    units: List[SourceUnit] = []
    ordinal = 0
    current_section = "Body"

    try:
        for page_index in range(len(doc)):
            try:
                raw = doc[page_index].get_text("text")
            except Exception as exc:
                logger.warning("page_extract_failed page=%s error=%s", page_index + 1, exc)
                continue
            if not raw or not raw.strip():
                continue

            # Group the page's lines into (section, text) runs.
            buffer: List[str] = []
            runs: List[Tuple[str, str]] = []
            for line in raw.splitlines():
                if _looks_like_heading(line):
                    if buffer:
                        runs.append((current_section, "\n".join(buffer)))
                        buffer = []
                    current_section = _canonical_section(line)
                else:
                    buffer.append(line)
            if buffer:
                runs.append((current_section, "\n".join(buffer)))

            for section, body in runs:
                words = _split_words(body)
                if not words:
                    continue
                start = 0
                while start < len(words):
                    piece = " ".join(words[start:start + _UNIT_WORDS]).strip()
                    if piece:
                        # Content wins over the detected heading here: a
                        # missed "References" heading would otherwise leave a
                        # whole bibliography labelled "Methodology".
                        unit_section = (
                            "References" if looks_like_references(piece) else section
                        )
                        units.append(SourceUnit(
                            ordinal=ordinal,
                            text=piece,
                            page=page_index + 1,
                            section=unit_section,
                        ))
                        ordinal += 1
                    start += (_UNIT_WORDS - _UNIT_OVERLAP)
    finally:
        doc.close()

    if not units:
        raise CompilationError("No extractable text found in PDF.")
    return units


def locate_evidence(
    evidence: str, units: Sequence[SourceUnit]
) -> Tuple[List[int], List[str]]:
    """Map a quote back to the source units it came from.

    Matching is deliberately strict-ish: the quote is normalized and looked up
    whole, then by its longest interior window. A quote that matches nothing
    means the model produced text the paper does not contain, which is exactly
    the signal the caller needs.
    """
    if not evidence or len(evidence.strip()) < _MIN_EVIDENCE_CHARS or not units:
        return [], []

    needle = _normalize(evidence)
    pages: List[int] = []
    keys: List[str] = []

    def _record(unit: SourceUnit) -> None:
        if unit.page is not None and unit.page not in pages:
            pages.append(unit.page)
        key = source_entry_key(unit)
        if key not in keys:
            keys.append(key)

    for unit in units:
        if needle in unit.normalized:
            _record(unit)

    if keys:
        return pages, keys

    # PDFs reflow text, so an exact quote can straddle a unit boundary. Fall
    # back to the quote's longest distinctive window before giving up.
    words = needle.split()
    if len(words) >= 6:
        window = " ".join(words[: max(6, len(words) // 2)])
        for unit in units:
            if window and window in unit.normalized:
                _record(unit)

    return pages, keys


# ── Deterministic keys ────────────────────────────────────────────────────────
# Recompiling a paper must overwrite its rows, never duplicate them, and a
# citation issued last week must still resolve. Both follow from the key being
# a pure function of (paper, kind, position).

def _source_key(paper_id: str, ordinal: int) -> str:
    return f"{paper_id}::source::{ordinal}"


def source_entry_key(unit: SourceUnit) -> str:
    return _source_key(unit.paper_id, unit.ordinal)


def _compiled_key(paper_id: str, field_key: str) -> str:
    return f"{paper_id}::compiled::{field_key}"


def _term_key(paper_id: str, kind: str, slug: str) -> str:
    return f"{paper_id}::{kind}::{slug}"


def slugify(name: str) -> str:
    slug = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", slug).strip("-").lower()
    return slug[:120] or "unnamed"


# ── Markdown rendering ────────────────────────────────────────────────────────

def _yaml_list(values: Sequence[str]) -> str:
    if not values:
        return "[]"
    return "[" + ", ".join(json_safe(v) for v in values) + "]"


def json_safe(value: str) -> str:
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def render_knowledge_page(
    paper: Paper,
    fields: Sequence[CompiledField],
    concepts: Sequence[Dict[str, Any]],
    methods: Sequence[Dict[str, Any]],
    topics: Sequence[str],
    units: Sequence[SourceUnit],
) -> str:
    """Render the LLM-Wiki page: YAML frontmatter + readable sections.

    Provenance is rendered inline per section rather than collected in a
    footnote block, because the page is meant to be readable on its own — a
    reader should be able to see which claim rests on which page of the source
    without cross-referencing.
    """
    authors: List[str] = []
    raw_authors = getattr(paper, "authors", None)
    if isinstance(raw_authors, list):
        authors = [str(a) for a in raw_authors if a]
    elif isinstance(raw_authors, str) and raw_authors.strip():
        authors = [a.strip() for a in raw_authors.split(",") if a.strip()]

    lines: List[str] = ["---"]
    lines.append(f"paper_id: {paper.id}")
    lines.append(f"title: {json_safe(paper.title or 'Untitled')}")
    lines.append(f"authors: {_yaml_list(authors)}")
    lines.append(f"year: {paper.publication_year if paper.publication_year else 'null'}")
    lines.append(f"venue: {json_safe(paper.venue or '')}")
    lines.append(f"doi: {json_safe(paper.doi or '')}")
    lines.append(f"arxiv_id: {json_safe(paper.arxiv_id or '')}")
    lines.append(f"source_document: {json_safe(paper.pdf_url or '')}")
    lines.append(f"topics: {_yaml_list(topics)}")
    lines.append(f"methods: {_yaml_list([m['name'] for m in methods])}")
    lines.append(f"concepts: {_yaml_list([c['name'] for c in concepts])}")
    lines.append(f"source_units: {len(units)}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {paper.title or 'Untitled'}")
    lines.append("")

    for f in fields:
        lines.append(f"## {f.heading}")
        lines.append("")
        if not f.text:
            lines.append("_Not covered by the source document._")
            lines.append("")
            continue
        lines.append(f.text)
        lines.append("")
        if f.evidence:
            marker = "" if f.verified else " _(unverified — quote not located in source)_"
            pages = ", ".join(str(p) for p in f.pages) or "n/a"
            lines.append(f"> {f.evidence}")
            lines.append("")
            lines.append(f"— source page(s): {pages}{marker}")
            lines.append("")

    if concepts:
        lines.append("## Key Concepts")
        lines.append("")
        for c in concepts:
            desc = f" — {c['description']}" if c.get("description") else ""
            lines.append(f"- **{c['name']}**{desc}")
        lines.append("")

    if methods:
        lines.append("## Methods Used")
        lines.append("")
        for m in methods:
            desc = f" — {m['description']}" if m.get("description") else ""
            lines.append(f"- **{m['name']}**{desc}")
        lines.append("")

    if topics:
        lines.append("## Topics")
        lines.append("")
        lines.extend(f"- {t}" for t in topics)
        lines.append("")

    lines.append("## Evidence / Source References")
    lines.append("")
    lines.append(
        f"Compiled from {len(units)} verbatim source units extracted from "
        f"`{paper.pdf_url or 'the source PDF'}`."
    )
    lines.append("")
    sections_seen: List[str] = []
    for u in units:
        if u.section not in sections_seen:
            sections_seen.append(u.section)
    lines.append("Detected sections: " + ", ".join(sections_seen))
    lines.append("")

    return "\n".join(lines)


# ── Compiler ──────────────────────────────────────────────────────────────────

class KnowledgeCompiler:

    async def compile_paper(
        self,
        db: AsyncSession,
        paper_id: str,
        pdf_bytes: bytes,
    ) -> CompilationResult:
        """Full pipeline for one paper. Replaces this paper's knowledge."""
        paper = await db.scalar(select(Paper).where(Paper.id == uuid.UUID(str(paper_id))))
        if paper is None:
            raise CompilationError(f"Paper {paper_id} not found")

        pid = str(paper.id)
        units = extract_source_units(pdf_bytes)
        for u in units:
            u.paper_id = pid

        result = CompilationResult(
            paper_id=pid, source_units=len(units), compiled_fields=0,
            verified_fields=0, concepts=0, methods=0, topics=0,
        )

        raw: Dict[str, Any] = {}
        try:
            raw = await self._compile_with_llm(paper, units)
        except LLMError as exc:
            # A failed compilation must not lose the source text: the paper is
            # still fully answerable from verbatim units, just without the
            # compiled overview. Degraded, not broken.
            result.degraded = True
            result.notes.append(f"llm_compilation_failed: {exc}")
            logger.warning("knowledge_compilation_degraded paper_id=%s error=%s", pid, exc)

        fields = self._build_fields(raw, units)
        concepts = self._build_terms(raw.get("concepts"), units, KIND_CONCEPT)
        methods = self._build_terms(raw.get("methods"), units, KIND_METHOD)
        topics = self._build_topics(raw.get("topics"))

        result.compiled_fields = sum(1 for f in fields if f.text)
        result.verified_fields = sum(1 for f in fields if f.text and f.verified)
        result.concepts = len(concepts)
        result.methods = len(methods)
        result.topics = len(topics)

        await self._persist(db, paper, units, fields, concepts, methods, topics)

        page = render_knowledge_page(paper, fields, concepts, methods, topics, units)
        try:
            result.page_path = await knowledge_store.write(paper_page_path(pid), page)
        except Exception as exc:
            # The index is the retrieval path; the Markdown page is the
            # portable artefact. Losing the page is a real problem but not one
            # that should discard a successful compilation.
            result.notes.append(f"page_write_failed: {exc}")
            logger.error("knowledge_page_write_failed paper_id=%s error=%s", pid, exc)

        logger.info("knowledge_compiled %s", result.to_log())
        return result

    @staticmethod
    def select_compile_units(units: Sequence[SourceUnit]) -> List[SourceUnit]:
        """Choose which source units the compilation call gets to see.

        Sections are visited in priority order and units are taken in document
        order within each, until the character budget is spent. Back matter is
        skipped outright. The result is returned in document order so the model
        reads the paper forwards rather than in priority order.

        Taking the head of the document instead — the obvious approach — spends
        the entire budget on the abstract and introduction and never reaches
        results or limitations, so those fields came back empty on every paper.
        """
        budget = settings.KNOWLEDGE_COMPILE_MAX_CHARS
        by_section: Dict[str, List[SourceUnit]] = {}
        for u in units:
            if u.section in _COMPILE_SKIP_SECTIONS:
                continue
            by_section.setdefault(u.section, []).append(u)

        ordered = [s for s in _COMPILE_SECTION_PRIORITY if s in by_section]
        ordered += [s for s in by_section if s not in _COMPILE_SECTION_PRIORITY]

        chosen: List[SourceUnit] = []
        used = 0
        for section in ordered:
            for u in by_section[section]:
                cost = len(u.text) + 60  # + the page/section header
                if used + cost > budget and chosen:
                    continue
                chosen.append(u)
                used += cost
        chosen.sort(key=lambda u: u.ordinal)
        return chosen

    async def _compile_with_llm(
        self, paper: Paper, units: Sequence[SourceUnit]
    ) -> Dict[str, Any]:
        blocks = [
            f"[page {u.page} | section: {u.section}]\n{u.text}"
            for u in self.select_compile_units(units)
        ]

        messages = build_knowledge_compilation_messages(
            {
                "id": str(paper.id),
                "title": paper.title,
                "abstract": paper.abstract,
                "publication_year": paper.publication_year,
                "venue": paper.venue,
            },
            "\n\n".join(blocks),
        )
        model = llm_provider.model_for("extraction")
        return await llm_provider.generate_json(
            model, messages, max_tokens=settings.KNOWLEDGE_COMPILE_MAX_TOKENS
        )

    def _build_fields(
        self, raw: Dict[str, Any], units: Sequence[SourceUnit]
    ) -> List[CompiledField]:
        fields: List[CompiledField] = []
        for key, heading in KNOWLEDGE_SECTIONS:
            value = raw.get(key)
            text, evidence = "", ""
            if isinstance(value, dict):
                text = str(value.get("text") or "").strip()
                evidence = str(value.get("evidence") or "").strip()
            elif isinstance(value, str):
                # Tolerate a model that returned a bare string. It carries no
                # evidence, so it will simply be unverified.
                text = value.strip()
            elif isinstance(value, list):
                text = "\n".join(f"- {v}" for v in value if v)

            pages, keys = locate_evidence(evidence, units)
            fields.append(CompiledField(
                key=key, heading=heading, text=text, evidence=evidence,
                pages=pages, entry_keys=keys,
            ))
        return fields

    def _build_terms(
        self, raw_terms: Any, units: Sequence[SourceUnit], kind: str
    ) -> List[Dict[str, Any]]:
        """Normalize extracted concepts/methods, dropping the ungrounded ones.

        Canonicalization is reused from `concept_service` rather than
        reimplemented — that module's alias folding and stopword rejection are
        the part of the old concept pipeline worth keeping, and they are pure
        functions with no Neo4j dependency.
        """
        from app.services.concept_service import canonical_key, display_name, is_valid_concept

        if not isinstance(raw_terms, list):
            return []

        out: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for item in raw_terms:
            if isinstance(item, str):
                name, description, evidence = item, "", ""
            elif isinstance(item, dict):
                name = str(item.get("name") or "").strip()
                description = str(item.get("description") or "").strip()
                evidence = str(item.get("evidence") or "").strip()
            else:
                continue
            if not name:
                continue

            key = canonical_key(name)
            if not key or key in seen or not is_valid_concept(name, key):
                continue
            seen.add(key)

            pages, entry_keys = locate_evidence(evidence, units)
            out.append({
                "concept_key": key,
                "name": display_name(name),
                "slug": slugify(key),
                "kind": kind,
                "description": description,
                "evidence": evidence,
                "pages": pages,
                "entry_keys": entry_keys,
            })
        return out

    def _build_topics(self, raw_topics: Any) -> List[str]:
        if not isinstance(raw_topics, list):
            return []
        out: List[str] = []
        for t in raw_topics:
            if isinstance(t, str) and t.strip() and t.strip() not in out:
                out.append(t.strip()[:120])
        return out[:8]

    async def _persist(
        self,
        db: AsyncSession,
        paper: Paper,
        units: Sequence[SourceUnit],
        fields: Sequence[CompiledField],
        concepts: Sequence[Dict[str, Any]],
        methods: Sequence[Dict[str, Any]],
        topics: Sequence[str],
    ) -> None:
        """Replace this paper's index rows in one transaction.

        Delete-then-insert rather than upsert: a recompilation can produce
        fewer units than last time (a shorter extraction, a different PDF),
        and leaving the surplus behind would let stale text keep matching
        searches. This is the same reasoning the old pipeline's chunk-prune
        step encoded.
        """
        pid = paper.id

        await db.execute(delete(KnowledgeEntry).where(KnowledgeEntry.paper_id == pid))
        await db.execute(delete(PaperConcept).where(PaperConcept.paper_id == pid))
        await db.execute(delete(ConceptRelation).where(ConceptRelation.paper_id == pid))

        source_file = paper.pdf_url or ""
        title = paper.title or ""

        for u in units:
            db.add(KnowledgeEntry(
                paper_id=pid,
                entry_key=_source_key(str(pid), u.ordinal),
                kind=KIND_SOURCE,
                title=title,
                section=u.section,
                body=u.text,
                page=u.page,
                ordinal=u.ordinal,
                provenance={
                    "source_file": source_file,
                    "page": u.page,
                    "section": u.section,
                    "source_text": u.text[:400],
                },
            ))

        # Compiled sections sit after the source units in ordinal space so a
        # document-order sort keeps verbatim text first.
        base = len(units)
        for offset, f in enumerate(fields):
            if not f.text:
                continue
            db.add(KnowledgeEntry(
                paper_id=pid,
                entry_key=_compiled_key(str(pid), f.key),
                kind=KIND_COMPILED,
                title=f"{title} — {f.heading}",
                section=f.heading,
                body=f.text,
                page=f.pages[0] if f.pages else None,
                ordinal=base + offset,
                provenance={
                    "source_file": source_file,
                    "pages": f.pages,
                    "section": f.heading,
                    "source_text": f.evidence,
                    "evidence_keys": f.entry_keys,
                    "verified": f.verified,
                },
            ))

        term_base = base + len(fields)
        for offset, term in enumerate(list(concepts) + list(methods)):
            db.add(PaperConcept(
                paper_id=pid,
                concept_key=term["concept_key"],
                name=term["name"],
                kind=term["kind"],
                description=term["description"] or None,
                evidence=term["evidence"] or None,
                pages=term["pages"],
                entry_keys=term["entry_keys"],
            ))
            body = term["description"] or term["name"]
            db.add(KnowledgeEntry(
                paper_id=pid,
                entry_key=_term_key(str(pid), term["kind"], term["slug"]),
                kind=term["kind"],
                slug=term["slug"],
                title=term["name"],
                section="Key Concepts" if term["kind"] == KIND_CONCEPT else "Methods Used",
                body=body,
                page=term["pages"][0] if term["pages"] else None,
                ordinal=term_base + offset,
                provenance={
                    "source_file": source_file,
                    "pages": term["pages"],
                    "source_text": term["evidence"],
                    "evidence_keys": term["entry_keys"],
                    "verified": bool(term["entry_keys"]),
                },
            ))

        topic_base = term_base + len(concepts) + len(methods)
        for offset, topic in enumerate(topics):
            db.add(KnowledgeEntry(
                paper_id=pid,
                entry_key=_term_key(str(pid), KIND_TOPIC, slugify(topic)),
                kind=KIND_TOPIC,
                slug=slugify(topic),
                title=topic,
                section="Topics",
                body=topic,
                ordinal=topic_base + offset,
                provenance={"source_file": source_file},
            ))

        await db.commit()


knowledge_compiler = KnowledgeCompiler()
