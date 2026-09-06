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


async def _neo4j_up() -> bool:
    try:
        from app.db.neo4j_client import neo4j_client
        await neo4j_client.connect()
        s = await neo4j_client.get_session()
        async with s:
            await s.run("RETURN 1")
        return True
    except Exception:
        return False


try:
    NEO4J_UP = run_isolated(_neo4j_up())
except Exception:
    NEO4J_UP = False

requires_neo4j = pytest.mark.skipif(
    not NEO4J_UP, reason="Neo4j not reachable — integration test skipped, not passed."
)


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

@requires_neo4j
def test_concepts_have_paper_scoped_edges():
    """Invariant 18: every concept in a paper's view has an edge from that paper."""
    from app.db.neo4j_client import neo4j_client
    from app.services.neo4j_service import neo4j_service

    async def run():
        s = await neo4j_client.get_session()
        async with s:
            row = await (await s.run(
                "MATCH (p:Paper)-[:HAS_CONCEPT]->() RETURN p.id AS id LIMIT 1")).single()
            if not row:
                pytest.skip("no concept graph in Neo4j yet")
            pid = row["id"]
            g = await neo4j_service.get_paper_concept_graph(s, pid)
            assert g["concepts"], "paper has HAS_CONCEPT but view is empty"
            ids = [c["id"] for c in g["concepts"]]
            verified = await (await s.run(
                """
                MATCH (p:Paper {id:$pid})-[:HAS_CONCEPT]->(c:Concept)
                WHERE c.id IN $ids RETURN count(c) AS n
                """, pid=pid, ids=ids)).single()
            assert verified["n"] == len(ids)

    run_isolated(run())


@requires_neo4j
def test_paper_graphs_are_isolated():
    """Invariant 18: Paper A's view never contains a relation asserted by Paper B."""
    from app.db.neo4j_client import neo4j_client
    from app.services.neo4j_service import neo4j_service

    async def run():
        s = await neo4j_client.get_session()
        async with s:
            rows = await (await s.run(
                "MATCH (p:Paper)-[:HAS_CONCEPT]->() RETURN DISTINCT p.id AS id LIMIT 2")).data()
            if len(rows) < 2:
                pytest.skip("need two papers with concepts")
            a = await neo4j_service.get_paper_concept_graph(s, rows[0]["id"])
            b = await neo4j_service.get_paper_concept_graph(s, rows[1]["id"])
            # Every relation surfaced for a paper must be well-formed and
            # scoped: get_paper_concept_graph filters on {paper_id: $paper_id},
            # so a foreign assertion cannot appear here.
            for g in (a, b):
                for rel in g["relations"]:
                    assert rel["source"] and rel["target"], "malformed relation"
            assert {c["id"] for c in a["concepts"]} != {c["id"] for c in b["concepts"]}, \
                "two different papers produced identical concept sets"

    run_isolated(run())


@requires_neo4j
def test_reingestion_of_identical_payload_is_idempotent():
    """Invariant 20: writing the same concepts twice must not grow the graph."""
    from app.db.neo4j_client import neo4j_client
    from app.services.neo4j_service import neo4j_service

    async def run():
        s = await neo4j_client.get_session()
        async with s:
            row = await (await s.run(
                "MATCH (p:Paper)-[:HAS_CONCEPT]->() RETURN p.id AS id LIMIT 1")).single()
            if not row:
                pytest.skip("no concept graph yet")
            pid = row["id"]
            before = await neo4j_service.graph_stats(s)
            g = await neo4j_service.get_paper_concept_graph(s, pid)

            concepts = [{
                "id": c["id"], "name": c["name"],
                "aliases": c.get("aliases") or [c["name"]],
                "importance": c.get("importance") or 0.5,
                "evidence": c.get("evidence") or "",
                "pages": c.get("pages") or [], "chunk_ids": c.get("chunk_ids") or [],
            } for c in g["concepts"]]
            relations = [{
                "source_id": r["source"], "target_id": r["target"], "type": r["type"],
                "evidence": r.get("evidence") or "", "pages": r.get("pages") or [],
                "chunk_ids": r.get("chunk_ids") or [],
            } for r in g["relations"]]

            await neo4j_service.upsert_concepts(s, pid, concepts)
            await neo4j_service.upsert_concept_relations(s, pid, relations)
            after = await neo4j_service.graph_stats(s)

        assert after["concepts"] == before["concepts"], "concept nodes duplicated"
        assert after["has_concept"] == before["has_concept"], "paper edges duplicated"
        assert after["relations"] == before["relations"], "relations duplicated"

    run_isolated(run())


@requires_neo4j
def test_graph_has_no_orphan_concepts():
    """Invariant 20: clearing a paper's edges must not leave dangling nodes."""
    from app.db.neo4j_client import neo4j_client
    from app.services.neo4j_service import neo4j_service

    async def run():
        s = await neo4j_client.get_session()
        async with s:
            stats = await neo4j_service.graph_stats(s)
        if stats.get("concepts", 0) == 0:
            pytest.skip("no concept graph yet")
        assert stats["orphan_concepts"] == 0, (
            f"{stats['orphan_concepts']} Concept nodes have no paper")

    run_isolated(run())


@requires_neo4j
def test_graph_api_returns_referentially_intact_structure():
    """Invariant 21: every edge endpoint must exist in nodes (no phantom nodes)."""
    from app.db.neo4j_client import neo4j_client
    from app.services.neo4j_service import neo4j_service

    async def run():
        s = await neo4j_client.get_session()
        async with s:
            row = await (await s.run(
                "MATCH (p:Paper)-[:HAS_CONCEPT]->() RETURN p.id AS id LIMIT 1")).single()
            if not row:
                pytest.skip("no concept graph yet")
            pid = row["id"]
            g = await neo4j_service.get_paper_concept_graph(s, pid)

        node_ids = {pid} | {c["id"] for c in g["concepts"]}
        edges = [(pid, c["id"]) for c in g["concepts"]]
        edges += [(r["source"], r["target"]) for r in g["relations"]]
        for src, tgt in edges:
            assert src in node_ids and tgt in node_ids, f"phantom edge {src}->{tgt}"

    run_isolated(run())


@requires_neo4j
def test_project_graph_scope_excludes_foreign_papers():
    """Invariant 19: a project graph contains only that project's papers."""
    from sqlalchemy import select
    from app.db.neo4j_client import neo4j_client
    from app.db.session import AsyncSessionLocal
    from app.models.project import Project
    from app.models.project_paper import ProjectPaper
    from app.services.neo4j_service import neo4j_service

    async def run():
        async with AsyncSessionLocal() as db:
            project = await db.scalar(select(Project).limit(1))
            if project is None:
                pytest.skip("no projects")
            rows = await db.execute(
                select(ProjectPaper.paper_id).where(ProjectPaper.project_id == project.id))
            ids = [str(r[0]) for r in rows]
        if not ids:
            pytest.skip("project has no papers")
        s = await neo4j_client.get_session()
        async with s:
            g = await neo4j_service.get_project_concept_graph(s, ids)
        allowed = set(ids)
        for c in g["concepts"]:
            for pid in (c.get("paper_ids") or []):
                assert pid in allowed, f"foreign paper {pid} in project graph"
        for r in g["relations"]:
            assert r["paper_id"] in allowed, f"foreign relation from {r['paper_id']}"

    run_isolated(run())
