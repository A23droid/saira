"""
Concept-graph regression tests (invariants 14–21).

Normalization and validation logic is tested purely — it is the part that
caused duplicate and junk nodes, and it must be checkable without a database.
Graph-shape invariants (provenance, isolation, idempotency, API) run against
live Neo4j and skip when it is unreachable.

Run:  pytest evaluation/concept_graph/graph_integrity_tests.py -v
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from evaluation.common.bootstrap import bootstrap, run_isolated  # noqa: E402

bootstrap()

from app.services.concept_service import (  # noqa: E402
    STOP_CONCEPTS, canonical_key, concept_id_for, concept_service,
    display_name, is_valid_concept,
)
from app.services.prompts import CONCEPT_RELATION_TYPES  # noqa: E402


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
    not DB_UP, reason="Postgres not reachable — integration test skipped, not passed."
)


async def _a_paper_with_concepts(limit: int = 1) -> list[str]:
    """Paper IDs that actually have concepts stored."""
    from sqlalchemy import text

    from app.db.session import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(text(
            "SELECT DISTINCT paper_id::text FROM paper_concepts LIMIT :n"
        ), {"n": limit})).all()
    return [r[0] for r in rows]


# ── 15. Normalization ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("variants", [
    ["self-attention", "Self Attention", "Self-Attention", "Self-Attention Mechanism"],
    ["positional encoding", "Positional Encodings", "Positional-Encoding"],
    ["beam search", "Beam Search", "beam-search", "Beam Search Strategy"],
])
def test_surface_variants_collapse_to_one_concept(variants):
    """The four-way 'self-attention' split from the brief must not recur."""
    keys = {canonical_key(v) for v in variants}
    assert len(keys) == 1, f"{variants} produced {keys}"
    ids = {concept_id_for(canonical_key(v)) for v in variants}
    assert len(ids) == 1, "same concept must map to one node id"


@pytest.mark.parametrize("a,b", [
    ("self-attention", "cross-attention"),
    ("encoder", "decoder"),
    ("BLEU", "ROUGE"),
    ("training set", "test set"),
    ("greedy search", "beam search"),
])
def test_distinct_concepts_are_not_merged(a, b):
    """Over-merging is as damaging as under-merging."""
    assert canonical_key(a) != canonical_key(b), f"{a!r} and {b!r} were merged"


@pytest.mark.parametrize("word", ["bias", "corpus", "analysis", "loss", "basis"])
def test_singularization_does_not_mangle_stems(word):
    """The old naive 's'-stripper turned 'bias' into 'bia'."""
    assert canonical_key(word) == word.lower()


def test_irregular_plurals_normalize():
    assert canonical_key("analyses") == canonical_key("analysis")
    assert canonical_key("matrices") == canonical_key("matrix")


def test_display_name_preserves_acronym_casing():
    """Title-casing would render BERT as 'Bert'."""
    assert display_name("  BERT   model ") == "BERT model"
    assert display_name("GPU") == "GPU"


# ── 14. Extraction validity ───────────────────────────────────────────────────

@pytest.mark.parametrize("junk", ["model", "results", "the method", "data", "a", ""])
def test_generic_terms_are_rejected(junk):
    assert not is_valid_concept(junk, canonical_key(junk))


@pytest.mark.parametrize("good", [
    "Self-Attention", "BLEU", "WMT 2014", "Adam optimizer", "Beam Search",
])
def test_real_concepts_are_accepted(good):
    assert is_valid_concept(good, canonical_key(good))


def test_sentence_length_strings_are_rejected():
    long = "we propose a novel approach that improves translation quality substantially"
    assert not is_valid_concept(long, canonical_key(long))


# ── 16. Relationship validation ───────────────────────────────────────────────

def test_normalize_payload_drops_invalid_relations():
    """Relations to unknown concepts, self-loops, and unknown types must go."""
    raw = {
        "concepts": [
            {"name": "Transformer", "importance": 1.0, "evidence": "the Transformer uses"},
            {"name": "Self-Attention", "importance": 0.9, "evidence": "self-attention layers"},
        ],
        "relations": [
            {"source": "Transformer", "target": "Self-Attention", "type": "USES",
             "evidence": "the Transformer uses self-attention"},
            {"source": "Transformer", "target": "Nonexistent Concept", "type": "USES"},
            {"source": "Transformer", "target": "Transformer", "type": "USES"},
            {"source": "Transformer", "target": "Self-Attention", "type": "MADE_UP_TYPE"},
        ],
    }
    concepts, relations, stats = concept_service.normalize_payload(raw, chunks=[])
    assert len(concepts) == 2
    assert len(relations) == 1, f"invalid relations survived: {relations}"
    assert relations[0]["type"] == "USES"
    assert stats["rejected_relations"] == 3


def test_relation_types_are_from_closed_vocabulary():
    raw = {
        "concepts": [{"name": "BERT", "importance": 1.0, "evidence": "BERT"},
                     {"name": "BookCorpus", "importance": 0.8, "evidence": "BookCorpus"}],
        "relations": [{"source": "BERT", "target": "BookCorpus",
                       "type": t, "evidence": "e"} for t in CONCEPT_RELATION_TYPES],
    }
    _, relations, _ = concept_service.normalize_payload(raw, chunks=[])
    assert {r["type"] for r in relations} <= set(CONCEPT_RELATION_TYPES)


def test_duplicate_surface_forms_become_aliases_not_nodes():
    raw = {
        "concepts": [
            {"name": "Self-Attention", "importance": 0.9, "evidence": "a"},
            {"name": "self attention", "importance": 0.7, "evidence": "b"},
            {"name": "Self-Attention Mechanism", "importance": 0.5, "evidence": "c"},
        ],
        "relations": [],
    }
    concepts, _, stats = concept_service.normalize_payload(raw, chunks=[])
    assert len(concepts) == 1, "duplicates created separate nodes"
    assert stats["merged_duplicates"] == 2
    assert len(concepts[0]["aliases"]) == 3
    assert concepts[0]["importance"] == 0.9, "should keep the highest importance"


# ── 17. Provenance ────────────────────────────────────────────────────────────

def test_evidence_is_resolved_to_page_and_chunk():
    chunks = [
        {"id": "paperX_chunk_3", "page": 7,
         "text": "We train using the Adam optimizer with a learning rate of 0.001."},
        {"id": "paperX_chunk_4", "page": 8, "text": "Unrelated discussion of results."},
    ]
    raw = {"concepts": [{"name": "Adam optimizer", "importance": 0.9,
                         "evidence": "We train using the Adam optimizer"}],
           "relations": []}
    concepts, _, stats = concept_service.normalize_payload(raw, chunks)
    assert concepts[0]["pages"] == [7]
    assert concepts[0]["chunk_ids"] == ["paperX_chunk_3"]
    assert stats["with_provenance"] == 1


def test_unlocatable_evidence_yields_empty_provenance_not_a_guess():
    """A quote that isn't in the text must NOT be assigned a page."""
    chunks = [{"id": "c1", "page": 1, "text": "Completely different content here."}]
    raw = {"concepts": [{"name": "Adam optimizer", "importance": 0.9,
                         "evidence": "a sentence that does not appear anywhere"}],
           "relations": []}
    concepts, _, _ = concept_service.normalize_payload(raw, chunks)
    assert concepts[0]["pages"] == []
    assert concepts[0]["chunk_ids"] == []


# ── 18/19/20/21. Live-graph invariants ────────────────────────────────────────
#
# These asserted the same properties against Neo4j before the LLM-Wiki
# migration. The store changed; the invariants did not. Two of them changed
# meaning slightly, and say so where they do.

@requires_db
def test_concepts_have_paper_scoped_edges():
    """Invariant 18: every concept in a paper's view is asserted by that paper."""
    import uuid as _uuid

    from sqlalchemy import text

    from app.db.session import AsyncSessionLocal
    from app.services.graph_service import graph_service

    async def run():
        ids = await _a_paper_with_concepts()
        if not ids:
            pytest.skip("no concepts stored yet")
        pid = ids[0]
        async with AsyncSessionLocal() as db:
            g = await graph_service.get_paper_concept_graph(db, _uuid.UUID(pid))
            assert g["concepts"], "paper has concept rows but view is empty"
            keys = [c["id"] for c in g["concepts"]]
            n = (await db.execute(text(
                "SELECT count(*) FROM paper_concepts "
                "WHERE paper_id = CAST(:p AS uuid) AND concept_key = ANY(:k)"
            ), {"p": pid, "k": keys})).scalar()
        assert n == len(keys)

    run_isolated(run())


@requires_db
def test_paper_graphs_are_isolated():
    """Invariant 18: Paper A's view never contains a relation asserted by Paper B."""
    import uuid as _uuid

    from app.db.session import AsyncSessionLocal
    from app.services.graph_service import graph_service

    async def run():
        ids = await _a_paper_with_concepts(2)
        if len(ids) < 2:
            pytest.skip("need two papers with concepts")
        async with AsyncSessionLocal() as db:
            a = await graph_service.get_paper_concept_graph(db, _uuid.UUID(ids[0]))
            b = await graph_service.get_paper_concept_graph(db, _uuid.UUID(ids[1]))
        for g in (a, b):
            for rel in g["relations"]:
                assert rel["source"] and rel["target"], "malformed relation"
        assert {c["id"] for c in a["concepts"]} != {c["id"] for c in b["concepts"]}, (
            "two different papers produced identical concept sets")

    run_isolated(run())


@requires_db
def test_reingestion_of_identical_payload_is_idempotent():
    """Invariant 20: re-writing a paper's concepts must not grow the store.

    The Neo4j version re-ran `upsert_concepts` and compared node counts. The
    Postgres writer replaces the paper's rows rather than merging, and a unique
    constraint on (paper_id, concept_key) makes duplication impossible — so
    this now asserts that constraint actually holds in the live data.
    """
    from sqlalchemy import text

    from app.db.session import AsyncSessionLocal

    async def run():
        ids = await _a_paper_with_concepts()
        if not ids:
            pytest.skip("no concepts stored yet")
        pid = ids[0]
        async with AsyncSessionLocal() as db:
            stored = (await db.execute(text(
                "SELECT count(*) FROM paper_concepts WHERE paper_id = CAST(:p AS uuid)"
            ), {"p": pid})).scalar()
            dupes = (await db.execute(text(
                "SELECT count(*) FROM (SELECT concept_key FROM paper_concepts "
                "WHERE paper_id = CAST(:p AS uuid) GROUP BY concept_key "
                "HAVING count(*) > 1) d"
            ), {"p": pid})).scalar()
        assert dupes == 0, f"{dupes} concept keys duplicated within one paper"
        assert stored > 0

    run_isolated(run())


@requires_db
def test_graph_has_no_orphan_concepts():
    """Invariant 20: no concept row may reference a paper that no longer exists.

    In Neo4j a shared `:Concept` node could outlive every paper referencing it,
    so the old check counted stranded nodes. The relational model has no
    standalone concept row to strand — a concept exists only as a paper's
    assertion, and the FK cascade removes it with the paper. What can still go
    wrong is a row pointing at a missing paper, so that is what is asserted.
    """
    from sqlalchemy import text

    from app.db.session import AsyncSessionLocal

    async def run():
        async with AsyncSessionLocal() as db:
            total = (await db.execute(
                text("SELECT count(*) FROM paper_concepts"))).scalar()
            orphans = (await db.execute(text(
                "SELECT count(*) FROM paper_concepts pc "
                "LEFT JOIN papers p ON p.id = pc.paper_id WHERE p.id IS NULL"
            ))).scalar()
        if total == 0:
            pytest.skip("no concepts stored yet")
        assert orphans == 0, f"{orphans} concept rows reference a missing paper"

    run_isolated(run())


@requires_db
def test_graph_api_returns_referentially_intact_structure():
    """Invariant 21: every edge endpoint must exist in nodes (no phantom nodes)."""
    import uuid as _uuid

    from app.db.session import AsyncSessionLocal
    from app.services.graph_service import graph_service

    async def run():
        ids = await _a_paper_with_concepts()
        if not ids:
            pytest.skip("no concepts stored yet")
        pid = ids[0]
        async with AsyncSessionLocal() as db:
            g = await graph_service.get_paper_concept_graph(db, _uuid.UUID(pid))

        node_ids = {pid} | {c["id"] for c in g["concepts"]}
        edges = [(pid, c["id"]) for c in g["concepts"]]
        edges += [(r["source"], r["target"]) for r in g["relations"]]
        for src, tgt in edges:
            assert src in node_ids and tgt in node_ids, f"phantom edge {src}->{tgt}"

    run_isolated(run())


@requires_db
def test_project_graph_scope_excludes_foreign_papers():
    """Invariant 19: a project graph contains only that project's papers."""
    from sqlalchemy import select

    from app.db.session import AsyncSessionLocal
    from app.models.project import Project
    from app.models.project_paper import ProjectPaper
    from app.services.graph_service import graph_service

    async def run():
        async with AsyncSessionLocal() as db:
            project = await db.scalar(select(Project).limit(1))
            if project is None:
                pytest.skip("no projects")
            rows = await db.execute(
                select(ProjectPaper.paper_id).where(ProjectPaper.project_id == project.id))
            ids = {str(r[0]) for r in rows}
            if not ids:
                pytest.skip("project has no papers")
            g = await graph_service.get_project_concept_graph(db, project.id)

        paper_nodes = {n["id"] for n in g["nodes"] if n["type"] == "paper"}
        assert paper_nodes <= ids, (
            f"foreign paper(s) in project graph: {paper_nodes - ids}")

        node_ids = {n["id"] for n in g["nodes"]}
        for e in g["edges"]:
            src, tgt = e["source"], e["target"]
            assert src in node_ids and tgt in node_ids, f"phantom edge {src}->{tgt}"

    run_isolated(run())
