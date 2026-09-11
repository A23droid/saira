"""
Regression tests for the LLM-Wiki / OKF knowledge architecture.

Covers the four areas the migration brief requires: knowledge compilation,
retrieval, Project Chat and Paper Chat.

Two deliberate choices about what is and is not stubbed:

* **The PDF is real.** Each test builds a small but structurally realistic
  paper with PyMuPDF and runs the actual extractor over the actual bytes. A
  fixture of pre-chunked text would test nothing about section detection,
  which is where extraction actually goes wrong.
* **Generation is stubbed; everything around it is not.** The stub cites
  whatever evidence it is handed, so retrieval, scope enforcement, evidence
  budgeting and citation validation all run for real. That is where the
  scoping and grounding bugs live, and it keeps the suite deterministic and
  free of provider quota.

Requires live Postgres; skips (never silently passes) without it.
"""

from __future__ import annotations

import re
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from evaluation.common.bootstrap import bootstrap, run_isolated  # noqa: E402

bootstrap()

from fastapi.testclient import TestClient  # noqa: E402

from app.api.deps import get_current_user  # noqa: E402
from app.main import app  # noqa: E402


# ── Availability ──────────────────────────────────────────────────────────────

async def _db_up() -> bool:
    try:
        from sqlalchemy import text

        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


try:
    DB_UP = run_isolated(_db_up())
except Exception:
    DB_UP = False

requires_db = pytest.mark.skipif(
    not DB_UP, reason="Postgres not reachable — skipped, not passed."
)


# ── Synthetic papers ──────────────────────────────────────────────────────────

def _make_pdf(title: str, sections: list[tuple[str, str]]) -> bytes:
    """Render a small paper. One section per page, heading on its own line."""
    import pymupdf

    doc = pymupdf.open()
    for heading, body in sections:
        page = doc.new_page()
        y = 72
        page.insert_text((72, y), heading, fontsize=14)
        y += 24
        # Wrap by hand: insert_text does not, and a single long line would
        # leave the page and never be extracted.
        for line in _wrap(body, 88):
            page.insert_text((72, y), line, fontsize=10)
            y += 13
    data = doc.tobytes()
    doc.close()
    return data


def _wrap(text: str, width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines


#: A paper about tortoise navigation. The vocabulary is deliberately unusual so
#: a retrieval hit cannot come from anywhere else in the database.
PAPER_A = [
    ("Abstract", (
        "We present Chelonian Path Integration, a navigation model for slow-moving "
        "reptiles. Our tortoise navigation benchmark shows that carapace-mounted "
        "odometry outperforms visual landmarks in dense undergrowth."
    )),
    ("1 Introduction", (
        "Terrestrial chelonians navigate over long distances despite limited visual "
        "acuity. Prior work on carapace odometry has been anecdotal. We introduce a "
        "quantitative benchmark for tortoise navigation."
    )),
    ("2 Methodology", (
        "Chelonian Path Integration combines carapace-mounted accelerometry with a "
        "drift-correction filter. Each stride is integrated over the shell axis and "
        "corrected against a magnetometer reading every twelve seconds."
    )),
    ("3 Dataset", (
        "The Undergrowth corpus contains four hundred tortoise trajectories recorded "
        "across three seasons. Each trajectory carries ground-truth position from a "
        "differential GPS collar."
    )),
    ("4 Results", (
        "Chelonian Path Integration reduces mean positional error to eleven "
        "centimetres, compared with thirty-four centimetres for the visual landmark "
        "baseline on the Undergrowth corpus."
    )),
    ("References", (
        "Aldabra, G. et al. 2019. Shell dynamics. In Proceedings of the Conference on "
        "Reptile Locomotion, pages 55-70. arXiv:1901.00001. Galapagos, T. et al. 2021. "
        "Slow navigation. In Proceedings of the Conference on Herpetology, pages "
        "101-118. doi:10.1000/xyz. Testudo, R. et al. 2020. Carapace sensing, pages 3-19."
    )),
]

#: A second, unrelated paper. Nothing here should ever surface in Paper A's chat.
PAPER_B = [
    ("Abstract", (
        "We describe Volcanic Ash Spectrometry, a technique for classifying tephra "
        "deposits. The Krakatoa sampling protocol yields reproducible grain-size "
        "distributions."
    )),
    ("1 Methodology", (
        "Volcanic Ash Spectrometry irradiates tephra samples and measures scattered "
        "photon counts. The Krakatoa sampling protocol specifies a fixed sieve stack."
    )),
    ("2 Results", (
        "Grain-size classification accuracy reaches ninety-one percent on the "
        "Krakatoa reference deposits."
    )),
]


# ── Fixtures ──────────────────────────────────────────────────────────────────

async def _create_paper(title: str) -> str:
    from app.db.session import AsyncSessionLocal
    from app.models.paper import Paper

    async with AsyncSessionLocal() as db:
        paper = Paper(title=title, abstract="", source="test", pdf_url="test://synthetic")
        db.add(paper)
        await db.commit()
        await db.refresh(paper)
        return str(paper.id)


async def _delete_paper(paper_id: str) -> None:
    from app.db.session import AsyncSessionLocal
    from app.models.paper import Paper

    async with AsyncSessionLocal() as db:
        paper = await db.get(Paper, uuid.UUID(paper_id))
        if paper:
            await db.delete(paper)  # cascades to knowledge_entries + concepts
            await db.commit()


#: The compiler's LLM reply, shaped exactly like the prompt asks for. Two
#: fields quote the source verbatim and must verify; one quotes text that is
#: not in the paper and must NOT verify — that asymmetry is the whole point.
_COMPILED_REPLY = {
    "abstract": {
        "text": "A navigation model for slow reptiles.",
        "evidence": "We present Chelonian Path Integration, a navigation model for slow-moving reptiles.",
    },
    "research_problem": {
        "text": "Chelonians navigate well despite poor eyesight.",
        "evidence": "Terrestrial chelonians navigate over long distances despite limited visual acuity.",
    },
    "methodology": {
        "text": "Fabricated method description.",
        "evidence": "The system uses a quantum entanglement gyroscope calibrated against pulsar timing.",
    },
    "results": {
        "text": "Error drops to eleven centimetres.",
        "evidence": "reduces mean positional error to eleven centimetres",
    },
    "dataset": {"text": "", "evidence": ""},
    "experiments": {"text": "", "evidence": ""},
    "key_contributions": {"text": "", "evidence": ""},
    "limitations": {"text": "", "evidence": ""},
    "concepts": [
        {
            "name": "Chelonian Path Integration",
            "description": "Odometry-based navigation for tortoises",
            "evidence": "We present Chelonian Path Integration, a navigation model for slow-moving reptiles.",
        },
        {"name": "results", "description": "generic term that must be rejected", "evidence": ""},
    ],
    "methods": [
        {
            "name": "carapace-mounted accelerometry",
            "description": "Stride integration over the shell axis",
            "evidence": "combines carapace-mounted accelerometry with a drift-correction filter",
        },
    ],
    "topics": ["animal navigation", "sensor fusion"],
}


async def _compile(paper_id: str, sections: list, reply: dict | None = None):
    """Run the real compiler over a real PDF with generation stubbed."""
    from app.db.session import AsyncSessionLocal
    from app.services import llm_provider as lp
    from app.services.knowledge_compiler import knowledge_compiler

    pdf = _make_pdf("synthetic", sections)
    stub = AsyncMock(return_value=reply if reply is not None else _COMPILED_REPLY)
    async with AsyncSessionLocal() as db:
        with patch.object(lp.llm_provider, "generate_json", stub):
            return await knowledge_compiler.compile_paper(db, paper_id, pdf)


# ── 1. Knowledge compilation ──────────────────────────────────────────────────

def test_extraction_detects_sections_and_pages():
    """PDF → source units carrying a section label and a real page number."""
    from app.services.knowledge_compiler import extract_source_units

    units = extract_source_units(_make_pdf("t", PAPER_A))
    assert units, "no units extracted"

    sections = {u.section for u in units}
    assert "Abstract" in sections
    assert "Methodology" in sections, f"got {sections}"
    assert "Dataset" in sections
    assert all(u.page and u.page >= 1 for u in units), "unit without a page"
    assert all(u.text.strip() for u in units), "empty unit stored"


def test_bibliography_is_labelled_as_references():
    """Reference lists match almost any query, so they must be identifiable."""
    from app.services.knowledge_compiler import extract_source_units, looks_like_references

    units = extract_source_units(_make_pdf("t", PAPER_A))
    ref_units = [u for u in units if u.section == "References"]
    assert ref_units, "bibliography was not identified"
    assert all(looks_like_references(u.text) for u in ref_units)

    prose = [u for u in units if u.section == "Methodology"]
    assert prose and not any(looks_like_references(u.text) for u in prose), \
        "real prose misclassified as bibliography"


def test_evidence_located_in_source_verifies_and_invented_evidence_does_not():
    """The anti-hallucination mechanism, tested in both directions."""
    from app.services.knowledge_compiler import extract_source_units, locate_evidence

    units = extract_source_units(_make_pdf("t", PAPER_A))
    for u in units:
        u.paper_id = "11111111-1111-1111-1111-111111111111"

    pages, keys = locate_evidence(
        "Terrestrial chelonians navigate over long distances despite limited visual acuity.",
        units,
    )
    assert keys, "a verbatim quote from the paper failed to locate"
    assert pages and all(p >= 1 for p in pages)

    pages, keys = locate_evidence(
        "The system uses a quantum entanglement gyroscope calibrated against pulsar timing.",
        units,
    )
    assert keys == [] and pages == [], "invented evidence was accepted as grounded"


def test_compile_budget_skips_back_matter_and_respects_the_cap():
    from app.core.config import settings
    from app.services.knowledge_compiler import extract_source_units, knowledge_compiler

    units = extract_source_units(_make_pdf("t", PAPER_A))
    chosen = knowledge_compiler.select_compile_units(units)

    assert chosen, "nothing selected for compilation"
    assert all(u.section != "References" for u in chosen), "bibliography sent to the model"
    assert sum(len(u.text) for u in chosen) <= settings.KNOWLEDGE_COMPILE_MAX_CHARS + 500
    assert [u.ordinal for u in chosen] == sorted(u.ordinal for u in chosen), \
        "units must reach the model in document order"


@requires_db
def test_compilation_persists_a_knowledge_page_with_provenance():
    """Full pipeline: PDF → entries + concepts + Markdown page."""
    from sqlalchemy import text

    from app.db.session import AsyncSessionLocal
    from app.services.knowledge_store import knowledge_store, paper_page_path

    async def run():
        paper_id = await _create_paper("Chelonian navigation (test)")
        try:
            result = await _compile(paper_id, PAPER_A)
            assert result.source_units > 0
            assert result.compiled_fields >= 3
            assert result.concepts >= 1

            async with AsyncSessionLocal() as db:
                kinds = dict((await db.execute(text(
                    "SELECT kind, count(*) FROM knowledge_entries "
                    "WHERE paper_id = CAST(:p AS uuid) GROUP BY kind"
                ), {"p": paper_id})).all())
                assert kinds.get("source", 0) > 0
                assert kinds.get("compiled", 0) > 0

                verified = dict((await db.execute(text(
                    "SELECT section, provenance->>'verified' FROM knowledge_entries "
                    "WHERE paper_id = CAST(:p AS uuid) AND kind = 'compiled'"
                ), {"p": paper_id})).all())
                # Quoted from the paper → verified.
                assert verified.get("Abstract") == "true"
                assert verified.get("Results") == "true"
                # Quoted from nowhere → explicitly not verified, but retained.
                assert verified.get("Methodology") == "false", \
                    "an unlocatable quote was accepted as grounded"

                # The generic concept "results" must have been rejected.
                names = [r[0] for r in (await db.execute(text(
                    "SELECT name FROM paper_concepts WHERE paper_id = CAST(:p AS uuid)"
                ), {"p": paper_id})).all()]
                assert any("Chelonian" in n for n in names), names
                assert not any(n.lower() == "results" for n in names), \
                    "a generic term survived concept validation"

            page = await knowledge_store.read(paper_page_path(paper_id))
            assert page and page.startswith("---"), "no YAML frontmatter"
            assert f"paper_id: {paper_id}" in page
            assert "## Abstract" in page
            assert "unverified" in page, "unverified claim not flagged on the page"
        finally:
            await _delete_paper(paper_id)

    run_isolated(run())


@requires_db
def test_recompilation_replaces_rather_than_accumulates():
    """Deterministic keys + delete-then-insert: re-ingest must not double up."""
    from sqlalchemy import text

    from app.db.session import AsyncSessionLocal

    async def run():
        paper_id = await _create_paper("Idempotency (test)")
        try:
            await _compile(paper_id, PAPER_A)
            async with AsyncSessionLocal() as db:
                first = (await db.execute(text(
                    "SELECT count(*) FROM knowledge_entries WHERE paper_id = CAST(:p AS uuid)"
                ), {"p": paper_id})).scalar()

            await _compile(paper_id, PAPER_A)
            async with AsyncSessionLocal() as db:
                second = (await db.execute(text(
                    "SELECT count(*) FROM knowledge_entries WHERE paper_id = CAST(:p AS uuid)"
                ), {"p": paper_id})).scalar()
                dupes = (await db.execute(text(
                    "SELECT count(*) FROM (SELECT entry_key FROM knowledge_entries "
                    "WHERE paper_id = CAST(:p AS uuid) GROUP BY entry_key "
                    "HAVING count(*) > 1) d"
                ), {"p": paper_id})).scalar()

            assert second == first, f"entries grew from {first} to {second} on re-ingest"
            assert dupes == 0
        finally:
            await _delete_paper(paper_id)

    run_isolated(run())


@requires_db
def test_llm_failure_still_leaves_the_paper_answerable():
    """A compilation failure must degrade, not destroy: the verbatim source is
    indexed regardless, so the paper stays searchable without a wiki page."""
    from sqlalchemy import text

    from app.db.session import AsyncSessionLocal
    from app.services import llm_provider as lp
    from app.services.knowledge_compiler import knowledge_compiler
    from app.services.llm_provider import LLMError

    async def run():
        paper_id = await _create_paper("Degraded compilation (test)")
        try:
            pdf = _make_pdf("t", PAPER_A)
            boom = AsyncMock(side_effect=LLMError("provider is down"))
            async with AsyncSessionLocal() as db:
                with patch.object(lp.llm_provider, "generate_json", boom):
                    result = await knowledge_compiler.compile_paper(db, paper_id, pdf)

            assert result.degraded is True
            assert result.source_units > 0, "source text was lost on LLM failure"
            assert any("provider is down" in n for n in result.notes)

            async with AsyncSessionLocal() as db:
                n = (await db.execute(text(
                    "SELECT count(*) FROM knowledge_entries "
                    "WHERE paper_id = CAST(:p AS uuid) AND kind = 'source'"
                ), {"p": paper_id})).scalar()
            assert n > 0
        finally:
            await _delete_paper(paper_id)

    run_isolated(run())


@requires_db
def test_a_term_listed_as_both_concept_and_method_does_not_break_compilation():
    """`paper_concepts` is unique on (paper_id, concept_key), and models
    routinely list the same term under both `concepts` and `methods`. That
    inserted the key twice and failed the whole compilation with an
    IntegrityError — found on a real paper, where "reference free evaluation"
    appeared in both lists."""
    from sqlalchemy import text

    from app.db.session import AsyncSessionLocal

    overlapping = dict(_COMPILED_REPLY)
    overlapping["concepts"] = [
        {"name": "Chelonian Path Integration", "description": "nav model",
         "evidence": "We present Chelonian Path Integration, a navigation model for slow-moving reptiles."},
    ]
    overlapping["methods"] = [
        # Same canonical key as the concept above.
        {"name": "Chelonian Path Integration", "description": "also listed as a method",
         "evidence": "combines carapace-mounted accelerometry with a drift-correction filter"},
    ]

    async def run():
        a = await _create_paper("Concept/method overlap (test)")
        try:
            result = await _compile(a, PAPER_A, reply=overlapping)
            assert not result.degraded, result.notes
            async with AsyncSessionLocal() as db:
                rows = (await db.execute(text(
                    "SELECT concept_key, count(*) FROM paper_concepts "
                    "WHERE paper_id = CAST(:p AS uuid) GROUP BY concept_key"
                ), {"p": a})).all()
            assert rows, "nothing stored"
            assert all(n == 1 for _, n in rows), f"duplicate concept keys: {rows}"
        finally:
            await _delete_paper(a)

    run_isolated(run())


def test_control_characters_are_stripped_from_extracted_text():
    """PDFs contain control bytes, and Postgres rejects NUL in a text column.

    A real arXiv PDF extracted with 4 NUL bytes and 18 other control
    characters; storing that raised `invalid byte sequence for encoding
    "UTF8": 0x00` and failed the whole compilation. Neo4j tolerated them, so
    this failure mode arrived with the move to PostgreSQL.
    """
    from app.services.knowledge_compiler import strip_control

    dirty = "ab" + chr(0) + "cd" + chr(1) + "ef\tgh\nij" + chr(127) + "kl"
    assert strip_control(dirty) == "abcdef\tgh\nijkl"
    # Legitimate whitespace must survive.
    assert strip_control("a\tb\nc\rd") == "a\tb\nc\rd"
    assert strip_control("") == ""
    assert strip_control(None) == ""


@requires_db
def test_a_pdf_containing_nul_bytes_still_compiles():
    """End to end: text with NUL bytes must reach Postgres cleanly."""
    from sqlalchemy import text

    from app.db.session import AsyncSessionLocal

    nul = chr(0)
    dirty_sections = [
        ("Abstract", "We present Chelonian Path Integration" + nul +
                     ", a navigation model for slow" + chr(1) + "-moving reptiles."),
        ("2 Methodology", "Chelonian Path Integration combines carapace-mounted "
                          "accelerometry" + nul + " with a drift-correction filter."),
    ]

    async def run():
        a = await _create_paper("NUL bytes (test)")
        try:
            result = await _compile(
                a, dirty_sections,
                reply={"topics": [], "concepts": [], "methods": []},
            )
            assert result.source_units > 0, "extraction produced nothing"
            async with AsyncSessionLocal() as db:
                bodies = [r[0] for r in (await db.execute(text(
                    "SELECT body FROM knowledge_entries "
                    "WHERE paper_id = CAST(:p AS uuid) AND kind = 'source'"
                ), {"p": a})).all()]
            assert bodies, "nothing stored"
            assert not any(chr(0) in b for b in bodies), "NUL byte reached the database"
            assert any("Chelonian" in b for b in bodies), "text was lost, not cleaned"
        finally:
            await _delete_paper(a)

    run_isolated(run())


# ── 2. Retrieval ──────────────────────────────────────────────────────────────

@requires_db
def test_retrieval_ranks_relevant_content_and_scopes_to_the_paper():
    from app.db.session import AsyncSessionLocal
    from app.services.knowledge_retriever import knowledge_retriever

    async def run():
        a = await _create_paper("Tortoise navigation (test)")
        b = await _create_paper("Volcanic ash (test)")
        try:
            await _compile(a, PAPER_A)
            await _compile(b, PAPER_B, reply={"topics": [], "concepts": [], "methods": []})

            async with AsyncSessionLocal() as db:
                hits = await knowledge_retriever.search_paper(
                    db, "How is drift corrected during path integration?", a, top_k=5)
                assert hits, "no evidence retrieved"
                assert all(h.paper_id == a for h in hits), "SCOPE LEAK from another paper"
                assert any("drift-correction" in h.body for h in hits), \
                    [h.body[:60] for h in hits]
                assert all(0.0 <= h.score < 1.0 for h in hits), "score out of range"

                # Paper B's distinctive vocabulary must not reach Paper A's scope.
                leak = await knowledge_retriever.search_paper(
                    db, "Krakatoa sampling protocol tephra", a, top_k=5)
                assert all(h.paper_id == a for h in leak)
                assert not any("Krakatoa" in h.body for h in leak)

                # Project scope spans both.
                both = await knowledge_retriever.search_project(
                    db, "Krakatoa sampling protocol tephra", [a, b], top_k=5)
                assert any(h.paper_id == b for h in both), "project scope missed paper B"
        finally:
            await _delete_paper(a)
            await _delete_paper(b)

    run_isolated(run())


@requires_db
def test_retrieval_returns_nothing_rather_than_something_wrong():
    """A question the corpus cannot answer must yield no evidence, so the
    grounding policy makes the model abstain instead of improvising."""
    from app.db.session import AsyncSessionLocal
    from app.services.knowledge_retriever import knowledge_retriever

    async def run():
        a = await _create_paper("Empty-result (test)")
        try:
            await _compile(a, PAPER_A)
            async with AsyncSessionLocal() as db:
                hits = await knowledge_retriever.search_paper(
                    db, "zzzqqxwv unrelatedgibberish nonexistentterm", a, top_k=5)
                assert hits == [], [h.body[:50] for h in hits]

                assert await knowledge_retriever.search(db, "anything", [], top_k=5) == []
                assert await knowledge_retriever.search_paper(db, "   ", a, top_k=5) == []
        finally:
            await _delete_paper(a)

    run_isolated(run())


@requires_db
def test_metadata_filtering_by_kind():
    from app.db.session import AsyncSessionLocal
    from app.models.knowledge import KIND_SOURCE
    from app.services.knowledge_retriever import knowledge_retriever

    async def run():
        a = await _create_paper("Kind filter (test)")
        try:
            await _compile(a, PAPER_A)
            async with AsyncSessionLocal() as db:
                hits = await knowledge_retriever.search_paper(
                    db, "path integration navigation", a, top_k=8, kinds=[KIND_SOURCE])
                assert hits and all(h.kind == KIND_SOURCE for h in hits)
        finally:
            await _delete_paper(a)

    run_isolated(run())


@requires_db
def test_back_matter_does_not_outrank_the_papers_own_argument():
    """Bibliographies are dense in exactly the terms a question uses; before
    the section weighting they took the top slot on every query."""
    from app.db.session import AsyncSessionLocal
    from app.services.knowledge_retriever import knowledge_retriever

    async def run():
        a = await _create_paper("Ranking (test)")
        try:
            await _compile(a, PAPER_A)
            async with AsyncSessionLocal() as db:
                hits = await knowledge_retriever.search_paper(
                    db, "What navigation approach does this paper propose?", a, top_k=3)
                assert hits
                assert hits[0].section != "References", \
                    f"bibliography ranked first: {hits[0].body[:80]}"
        finally:
            await _delete_paper(a)

    run_isolated(run())


def test_generic_questions_expand_onto_sections():
    """The unit half of the fix for a real end-to-end failure.

    "What problem does this paper solve?" retrieved nothing: every content word
    is a stopword or absent from the paper's vocabulary. Papers state their
    problem, they do not use the word "problem".
    """
    from app.services.knowledge_retriever import build_terms, expand_with_sections

    q = "What problem does this paper solve?"
    terms = build_terms(q)
    assert terms == ["problem", "solve"], terms
    expanded = expand_with_sections(q, terms)
    assert "introduction" in expanded and "abstract" in expanded, expanded

    q = "What are the limitations?"
    assert "limitations" in expand_with_sections(q, build_terms(q))
    q = "How was it evaluated?"
    assert "experiments" in expand_with_sections(q, build_terms(q))


def test_specific_questions_are_not_expanded():
    """Expansion is noise for a question that already carries its own
    vocabulary, so it applies only below the generic-question threshold."""
    from app.services.knowledge_retriever import build_terms, expand_with_sections

    q = "Explain chelonian path integration drift correction magnetometer stride"
    terms = build_terms(q)
    assert len(terms) >= 5
    assert expand_with_sections(q, terms) == terms, "a specific question was expanded"


@requires_db
def test_generic_questions_retrieve_the_right_section():
    """The integration half: the expansion must actually land on the section."""
    from app.db.session import AsyncSessionLocal
    from app.services.knowledge_retriever import knowledge_retriever

    async def run():
        a = await _create_paper("Generic questions (test)")
        try:
            await _compile(a, PAPER_A)
            async with AsyncSessionLocal() as db:
                hits = await knowledge_retriever.search_paper(
                    db, "What problem does this paper solve?", a, top_k=3)
                assert hits, "a generic question still retrieves nothing"
                assert any(h.section in ("Abstract", "Introduction", "Research Problem")
                           for h in hits), [h.section for h in hits]

                hits = await knowledge_retriever.search_paper(
                    db, "What dataset was used?", a, top_k=3)
                assert hits and any(h.section in ("Dataset", "Experiments") for h in hits), \
                    [h.section for h in hits]
        finally:
            await _delete_paper(a)

    run_isolated(run())


@requires_db
def test_sql_layer_scopes_without_relying_on_the_python_guard():
    """Pin the *inner* scope filter, not just the final output.

    Retrieval has two independent scope barriers: the SQL WHERE clause and a
    Python drop-and-log guard after it. Asserting only on returned rows cannot
    tell them apart — removing either one alone still yields correct output,
    which was verified by mutating each in turn. This test fails if the SQL
    stops scoping, because the guard's ERROR log is the observable difference.
    """
    import logging

    from app.db.session import AsyncSessionLocal
    from app.services.knowledge_retriever import knowledge_retriever

    async def run():
        a = await _create_paper("SQL scope A (test)")
        b = await _create_paper("SQL scope B (test)")
        try:
            await _compile(a, PAPER_A)
            await _compile(b, PAPER_B, reply={"topics": [], "concepts": [], "methods": []})

            records: list[logging.LogRecord] = []

            class _Capture(logging.Handler):
                def emit(self, record):
                    records.append(record)

            logger = logging.getLogger("app.services.knowledge_retriever")
            handler = _Capture(level=logging.ERROR)
            logger.addHandler(handler)
            try:
                async with AsyncSessionLocal() as db:
                    # A query whose terms appear in BOTH papers, so an unscoped
                    # SQL query would certainly return the foreign one.
                    hits = await knowledge_retriever.search_paper(
                        db, "results protocol methodology accuracy", a, top_k=10)
            finally:
                logger.removeHandler(handler)

            violations = [r for r in records if "Scope violation" in r.getMessage()]
            assert not violations, (
                "the SQL query returned out-of-scope rows; only the Python guard "
                f"stopped them reaching the model: {[r.getMessage() for r in violations]}"
            )
            assert all(h.paper_id == a for h in hits)
        finally:
            await _delete_paper(a)
            await _delete_paper(b)

    run_isolated(run())


def test_python_guard_drops_a_foreign_row_the_sql_let_through():
    """Pin the *outer* barrier directly, by feeding the mapper a row the SQL
    should never have produced. Without this, deleting the guard as
    'redundant' would be invisible to the suite."""
    import logging
    from unittest.mock import MagicMock

    from app.services.knowledge_retriever import PostgresKnowledgeRetriever

    mine = "11111111-1111-1111-1111-111111111111"
    theirs = "22222222-2222-2222-2222-222222222222"

    def _row(pid, key):
        return {
            "entry_key": key, "paper_id": pid, "kind": "source", "title": "t",
            "section": "Methodology", "body": "body text", "page": 1, "ordinal": 0,
            "provenance": None, "paper_title": "T", "rank": 0.5,
        }

    class _Result:
        def mappings(self):
            return [_row(mine, "ok"), _row(theirs, "leak")]

    db = MagicMock()
    async def _execute(*a, **k):
        return _Result()
    db.execute = _execute

    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    logger = logging.getLogger("app.services.knowledge_retriever")
    handler = _Capture(level=logging.ERROR)
    logger.addHandler(handler)
    try:
        hits = run_isolated(
            PostgresKnowledgeRetriever().search(db, "anything", [mine], top_k=10))
    finally:
        logger.removeHandler(handler)

    assert [h.entry_key for h in hits] == ["ok"], "foreign row was not dropped"
    assert any("Scope violation" in r.getMessage() for r in records), \
        "the guard dropped the row silently; a leak would go unnoticed in production"


# ── 3 & 4. Chat, through the real HTTP endpoints ──────────────────────────────

async def _probe_user():
    from sqlalchemy import select

    from app.db.session import AsyncSessionLocal
    from app.models.user import User

    async with AsyncSessionLocal() as db:
        user = await db.scalar(select(User).limit(1))
        return str(user.id) if user else None


try:
    USER_ID = run_isolated(_probe_user())
except Exception:
    USER_ID = None

requires_user = pytest.mark.skipif(
    not DB_UP or not USER_ID, reason="no user in the database — skipped, not passed."
)


@pytest.fixture(scope="module")
def client():
    async def fake_user():
        from sqlalchemy import select

        from app.db.session import AsyncSessionLocal
        from app.models.user import User
        async with AsyncSessionLocal() as db:
            return await db.scalar(select(User).where(User.id == uuid.UUID(USER_ID)))

    previous = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = fake_user
    try:
        with TestClient(app) as c:
            yield c
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = previous
        # The TestClient portal owned an event loop the async engine pooled
        # connections against. Release them, or the next test module inherits
        # sockets bound to a dead loop and every test in it errors.
        import asyncio

        async def _dispose():
            from app.db.session import engine
            await engine.dispose()

        try:
            asyncio.run(_dispose())
        except Exception:
            pass


def _stub_generation(seen: list):
    """Cite the first evidence id actually supplied, plus one that never was."""
    async def stub(model, messages, **kwargs):
        joined = " ".join(m.get("content", "") for m in messages)
        ids = re.findall(r"evidence_id=([^\s|\]]+)", joined)
        seen.extend(ids)
        return {
            "answer": "Stubbed grounded answer.",
            "grounded": True,
            "abstained": False,
            "citations": (
                ([{"evidence_id": ids[0], "claim": "supported"}] if ids else [])
                + [{"evidence_id": "NEVER-SUPPLIED-999", "claim": "fabricated"}]
            ),
        }
    return stub


async def _make_project_with_papers(titles_sections: list) -> tuple[str, list[str]]:
    from app.db.session import AsyncSessionLocal
    from app.models.project import Project
    from app.models.project_paper import ProjectPaper

    paper_ids = []
    async with AsyncSessionLocal() as db:
        project = Project(user_id=uuid.UUID(USER_ID), name="Knowledge arch test project")
        db.add(project)
        await db.commit()
        await db.refresh(project)
        project_id = str(project.id)

    for title, sections in titles_sections:
        pid = await _create_paper(title)
        await _compile(pid, sections, reply=_COMPILED_REPLY if sections is PAPER_A else
                       {"topics": [], "concepts": [], "methods": []})
        paper_ids.append(pid)
        async with AsyncSessionLocal() as db:
            db.add(ProjectPaper(project_id=uuid.UUID(project_id), paper_id=uuid.UUID(pid)))
            await db.commit()

    return project_id, paper_ids


async def _cleanup(project_id: str, paper_ids: list[str]) -> None:
    from sqlalchemy import delete

    from app.db.session import AsyncSessionLocal
    from app.models.chat import ChatSession
    from app.models.project import Project

    async with AsyncSessionLocal() as db:
        await db.execute(delete(ChatSession).where(
            ChatSession.project_id == uuid.UUID(project_id)))
        for pid in paper_ids:
            await db.execute(delete(ChatSession).where(
                ChatSession.paper_id == uuid.UUID(pid)))
        project = await db.get(Project, uuid.UUID(project_id))
        if project:
            await db.delete(project)
        await db.commit()
    for pid in paper_ids:
        await _delete_paper(pid)


@requires_user
def test_paper_chat_answers_from_the_selected_paper_only(client):
    """Paper Chat: question → paper-scoped retrieval → context → grounded answer."""
    from app.services import ai_router as router_mod

    project_id, paper_ids = client.portal.call(
        _make_project_with_papers, [("Tortoise nav (chat test)", PAPER_A),
                                    ("Volcanic ash (chat test)", PAPER_B)])
    paper_a, paper_b = paper_ids
    try:
        r = client.post("/api/v1/chat/sessions", json={"paper_id": paper_a})
        assert r.status_code == 200, r.text
        session_id = r.json()["id"]

        seen: list[str] = []
        with patch.object(router_mod.groq_service, "chat_complete_json",
                          new=AsyncMock(side_effect=_stub_generation(seen))):
            r = client.post(f"/api/v1/chat/sessions/{session_id}/messages",
                            json={"question": "How is drift corrected during path integration?"})
        assert r.status_code == 200, r.text
        ai = r.json()["ai_message"]

        assert seen, "no evidence reached the model"
        assert ai["citations"], "no citations returned"

        supplied = {e["chunk_id"] for e in ai["evidence"]}
        for c in ai["citations"]:
            assert c["chunk_id"] in supplied, "citation not traceable to supplied evidence"
            assert c["paper_id"] == paper_a, "citation outside the paper scope"
        assert all(c["chunk_id"] != "NEVER-SUPPLIED-999" for c in ai["citations"]), \
            "fabricated citation survived validation"

        for e in ai["evidence"]:
            assert e["paper_id"] == paper_a, f"SCOPE LEAK: evidence from {e['paper_id']}"
        assert ai["retrieval"]["scope_type"] == "paper"
        assert ai["retrieval"]["paper_ids"] == [paper_a]

        # Follow-up: history must not widen the scope.
        with patch.object(router_mod.groq_service, "chat_complete_json",
                          new=AsyncMock(side_effect=_stub_generation(seen))):
            r = client.post(f"/api/v1/chat/sessions/{session_id}/messages",
                            json={"question": "And what dataset was that measured on?"})
        assert r.status_code == 200, r.text
        follow = r.json()["ai_message"]
        for e in follow["evidence"]:
            assert e["paper_id"] == paper_a, "follow-up leaked another paper"

        r = client.get(f"/api/v1/chat/sessions/{session_id}")
        assert r.status_code == 200
        assert len(r.json()["messages"]) == 4, "conversation history not persisted"
    finally:
        client.portal.call(_cleanup, project_id, paper_ids)


@requires_user
def test_project_chat_retrieves_across_multiple_papers(client):
    """Project Chat: question → project-wide retrieval → grounded answer."""
    from app.services import ai_router as router_mod

    project_id, paper_ids = client.portal.call(
        _make_project_with_papers, [("Tortoise nav (proj test)", PAPER_A),
                                    ("Volcanic ash (proj test)", PAPER_B)])
    try:
        seen: list[str] = []
        with patch.object(router_mod.groq_service, "chat_complete_json",
                          new=AsyncMock(side_effect=_stub_generation(seen))):
            r = client.post(f"/api/v1/projects/{project_id}/ai/chat",
                            json={"message": "Krakatoa sampling protocol tephra grain size"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["answer"]
        assert seen, "no evidence reached the model"

        # The question is answerable only from paper B; project scope must reach it.
        assert any(c["paper_id"] == paper_ids[1] for c in body["citations"]), \
            "project chat did not retrieve from the second paper"

        allowed = set(paper_ids)
        for c in body["citations"]:
            assert c["paper_id"] in allowed, "citation outside the project"

        session_id = body.get("session_id")
        assert session_id, "no session returned"

        with patch.object(router_mod.groq_service, "chat_complete_json",
                          new=AsyncMock(side_effect=_stub_generation(seen))):
            r = client.post(f"/api/v1/projects/{project_id}/ai/chat",
                            json={"message": "And how does the tortoise work compare?",
                                  "session_id": session_id})
        assert r.status_code == 200, r.text
        assert r.json()["session_id"] == session_id, "follow-up started a new session"
    finally:
        client.portal.call(_cleanup, project_id, paper_ids)


@requires_user
def test_project_chat_rejects_a_project_the_user_does_not_own(client):
    """Scope is resolved from the verified project, never from the request."""
    r = client.post(f"/api/v1/projects/{uuid.uuid4()}/ai/chat", json={"message": "hello"})
    assert r.status_code == 404, r.text


@requires_user
def test_empty_project_is_reported_not_improvised(client):
    from app.db.session import AsyncSessionLocal
    from app.models.project import Project

    async def _make():
        async with AsyncSessionLocal() as db:
            p = Project(user_id=uuid.UUID(USER_ID), name="Empty (test)")
            db.add(p)
            await db.commit()
            await db.refresh(p)
            return str(p.id)

    async def _drop(pid):
        async with AsyncSessionLocal() as db:
            p = await db.get(Project, uuid.UUID(pid))
            if p:
                await db.delete(p)
                await db.commit()

    project_id = client.portal.call(_make)
    try:
        r = client.post(f"/api/v1/projects/{project_id}/ai/chat",
                        json={"message": "what is in this project?"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["grounded"] is False
        assert body["citations"] == []
        assert "no papers" in body["answer"].lower()
    finally:
        client.portal.call(_drop, project_id)


@requires_user
def test_a_degraded_compilation_stays_retryable(client):
    """A paper can be `indexed` and still carry an error: compilation degrades
    to source-only when the LLM call fails. That used to be permanent, because
    only FAILED_STATES were retryable — so one transient provider outage cost
    the paper its knowledge page forever. Found in end-to-end testing."""
    from sqlalchemy import select

    from app.db.session import AsyncSessionLocal
    from app.models.paper import Paper

    async def _mark_degraded(pid: str):
        async with AsyncSessionLocal() as db:
            paper = await db.scalar(select(Paper).where(Paper.id == uuid.UUID(pid)))
            paper.indexing_status = "indexed"
            paper.indexing_error = "llm_compilation_failed: provider was down"
            await db.commit()

    paper_id = client.portal.call(_create_paper, "Degraded retry (test)")
    try:
        client.portal.call(_mark_degraded, paper_id)
        r = client.get(f"/api/v1/papers/{paper_id}/indexing-status")
        assert r.status_code == 200, r.text
        body = r.json()

        assert body["indexing_status"] == "indexed"
        assert body["ask_ai_ready"] is True, "source text is still answerable"
        assert body["degraded"] is True, "degraded compilation not reported"
        assert body["can_retry"] is True, "a degraded paper can never be repaired"
    finally:
        client.portal.call(_delete_paper, paper_id)
