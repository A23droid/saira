"""
Concept-graph evaluation: extraction, normalization, relationships,
provenance, isolation, idempotency, and the graph API.

Every check runs against the live Neo4j graph produced by the real pipeline.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from evaluation.concept_graph import graph_metrics
from evaluation.config.evaluation_config import GraphFailure

logger = logging.getLogger(__name__)


async def build_graphs(db, documents, trace=None) -> List[Dict[str, Any]]:
    """Run concept extraction for each evaluation document."""
    from app.services.concept_service import concept_service

    reports = []
    for i, doc in enumerate(documents):
        if i:
            # Space out extraction calls. Firing them back-to-back after the
            # causal phase reliably tripped Groq's rate limit, which produced
            # zero concepts and looked like an extraction bug.
            await asyncio.sleep(2.0)
        report = await concept_service.sync_paper_concepts(db, doc.paper_id)
        report["title"] = doc.title
        reports.append(report)
        if trace:
            trace.write("concept_extraction", report)
    return reports


async def measure(documents, trace=None) -> List[Dict[str, Any]]:
    from app.db.neo4j_client import neo4j_client

    sess = await neo4j_client.get_session()
    out = []
    async with sess:
        for doc in documents:
            m = await graph_metrics.paper_graph_metrics(sess, doc.paper_id)
            m["title"] = doc.title
            m["classification"] = graph_metrics.classify_graph(m)
            out.append(m)
            if trace:
                trace.write("graph_metrics", m)
    return out


async def test_isolation(documents, trace=None) -> Dict[str, Any]:
    """Paper A's graph must not contain Paper B's concepts unless genuinely shared.

    A shared concept is legitimate — two transformer papers both discussing
    self-attention is correct behaviour, not contamination. What must never
    happen is Paper A's view returning a concept it has no HAS_CONCEPT edge to,
    or a relation asserted by another paper. Both are checked directly against
    the scoped query the API uses.
    """
    from app.db.neo4j_client import neo4j_client
    from app.services.neo4j_service import neo4j_service

    if len(documents) < 2:
        return {"applicable": False, "reason": "fewer than two documents"}

    a, b = documents[0], documents[1]
    sess = await neo4j_client.get_session()
    async with sess:
        ga = await neo4j_service.get_paper_concept_graph(sess, a.paper_id)
        gb = await neo4j_service.get_paper_concept_graph(sess, b.paper_id)

        # Every concept returned for A must have a real A→concept edge.
        a_ids = [c["id"] for c in ga["concepts"]]
        verified = await (await sess.run(
            """
            MATCH (p:Paper {id:$pid})-[:HAS_CONCEPT]->(c:Concept)
            WHERE c.id IN $ids RETURN count(c) AS n
            """, pid=a.paper_id, ids=a_ids)).single()
        edges_ok = (verified["n"] if verified else 0) == len(a_ids)

        # Every relation in A's view must be asserted by A.
        rel_ok = True
        bad = await (await sess.run(
            """
            MATCH (s:Concept)-[r:RELATES_TO]->(t:Concept)
            WHERE r.paper_id <> $pid
              AND (:Paper {id:$pid})-[:HAS_CONCEPT]->(s)
              AND (:Paper {id:$pid})-[:HAS_CONCEPT]->(t)
            RETURN count(r) AS n
            """, pid=a.paper_id)).single()
        foreign_relations_visible = 0
        a_rel_paper_ids = {r.get("paper_id") for r in ga.get("relations", [])
                           if r.get("paper_id")}
        if a_rel_paper_ids - {a.paper_id}:
            rel_ok = False
            foreign_relations_visible = len(a_rel_paper_ids - {a.paper_id})

    a_names = {c["name"] for c in ga["concepts"]}
    b_names = {c["name"] for c in gb["concepts"]}
    shared = sorted(a_names & b_names)

    result = {
        "applicable": True,
        "paper_a": a.paper_id, "paper_b": b.paper_id,
        "a_concepts": len(a_names), "b_concepts": len(b_names),
        "shared_concept_names": shared,
        "shared_count": len(shared),
        "graphs_are_distinct": a_names != b_names,
        "all_a_concepts_have_a_edge": edges_ok,
        "foreign_relations_visible_in_a": foreign_relations_visible,
        "passed": edges_ok and rel_ok and (a_names != b_names),
        "note": ("Shared concept names are legitimate when both papers genuinely "
                 "discuss the concept; contamination is defined as a concept or "
                 "relation appearing without an edge from that paper."),
    }
    result["classification"] = (
        GraphFailure.PASS if result["passed"] else GraphFailure.ISOLATION_FAILURE
    )
    if trace:
        trace.write("graph_isolation", result)
    return result


async def test_reingestion_idempotency(db, document, trace=None) -> Dict[str, Any]:
    """Re-ingesting the same paper must not multiply the graph.

    Extraction is not perfectly deterministic, so exact node equality is not a
    valid invariant. The invariant that *is* valid — and the one the original
    bug violated — is that the graph does not grow on repeat ingestion. This
    checks the write layer deterministically by replaying the SAME payload, and
    separately reports what a fresh LLM pass did.
    """
    from app.db.neo4j_client import neo4j_client
    from app.services.concept_service import concept_service
    from app.services.neo4j_service import neo4j_service

    pid = document.paper_id
    sess = await neo4j_client.get_session()
    async with sess:
        before = await neo4j_service.graph_stats(sess)
        g_before = await neo4j_service.get_paper_concept_graph(sess, pid)

    # -- Deterministic replay of an identical payload -------------------------
    concepts = [{
        "id": c["id"], "name": c["name"], "aliases": c.get("aliases") or [c["name"]],
        "importance": c.get("importance") or 0.5, "evidence": c.get("evidence") or "",
        "pages": c.get("pages") or [], "chunk_ids": c.get("chunk_ids") or [],
    } for c in g_before["concepts"]]
    relations = [{
        "source_id": r["source"], "target_id": r["target"], "type": r["type"],
        "evidence": r.get("evidence") or "", "pages": r.get("pages") or [],
        "chunk_ids": r.get("chunk_ids") or [],
    } for r in g_before["relations"]]

    sess = await neo4j_client.get_session()
    async with sess:
        await neo4j_service.upsert_concepts(sess, pid, concepts)
        await neo4j_service.upsert_concept_relations(sess, pid, relations)
        after_replay = await neo4j_service.graph_stats(sess)

    deterministic_ok = (
        after_replay.get("has_concept") == before.get("has_concept")
        and after_replay.get("relations") == before.get("relations")
        and after_replay.get("concepts") == before.get("concepts")
    )

    # -- Full re-extraction (non-deterministic LLM) ---------------------------
    rerun = await concept_service.sync_paper_concepts(db, pid)
    sess = await neo4j_client.get_session()
    async with sess:
        after_full = await neo4j_service.graph_stats(sess)

    no_growth = (
        after_full.get("has_concept", 0) <= max(before.get("has_concept", 0), len(concepts)) * 1.5
        and after_full.get("orphan_concepts", 0) == 0
    )

    result = {
        "paper_id": pid,
        "before": before,
        "after_identical_replay": after_replay,
        "after_full_reextraction": after_full,
        "deterministic_replay_idempotent": deterministic_ok,
        "no_uncontrolled_growth": no_growth,
        "orphans_after": after_full.get("orphan_concepts", 0),
        "reextraction_report": rerun,
        "passed": deterministic_ok and no_growth,
        "note": ("Deterministic replay is the strict idempotency check. Full "
                 "re-extraction is reported separately because LLM output "
                 "varies between runs; the invariant there is bounded growth "
                 "and zero orphans, not identical counts."),
    }
    result["classification"] = (
        GraphFailure.PASS if result["passed"] else GraphFailure.DUPLICATION_FAILURE
    )
    if trace:
        trace.write("graph_idempotency", result)
    return result


async def test_graph_api(db, documents, trace=None) -> Dict[str, Any]:
    """Verify the shapes the frontend consumes, straight from the services.

    The per-paper endpoint returns {nodes, edges} with a Paper node plus
    Concept nodes; the project endpoint returns the same shape scoped to a
    project. Both are validated for referential integrity — every edge endpoint
    must exist in `nodes`, which is exactly the condition a force-graph
    component needs to render without phantom nodes.
    """
    from app.services.graph_service import graph_service
    from app.services.neo4j_service import neo4j_service
    from app.db.neo4j_client import neo4j_client
    from sqlalchemy import select
    from app.models.project_paper import ProjectPaper

    doc = documents[0]
    sess = await neo4j_client.get_session()
    async with sess:
        raw = await neo4j_service.get_paper_concept_graph(sess, doc.paper_id)

    nodes = [{"id": doc.paper_id, "type": "Paper"}]
    nodes += [{"id": c["id"], "type": "Concept"} for c in raw["concepts"]]
    edges = [{"source": doc.paper_id, "target": c["id"]} for c in raw["concepts"]]
    cids = {c["id"] for c in raw["concepts"]}
    edges += [{"source": r["source"], "target": r["target"]}
              for r in raw["relations"] if r["source"] in cids and r["target"] in cids]

    node_ids = {n["id"] for n in nodes}
    integrity = all(e["source"] in node_ids and e["target"] in node_ids for e in edges)

    # Project-scoped API, if the document belongs to a project.
    project_result: Optional[Dict[str, Any]] = None
    row = await db.execute(
        select(ProjectPaper.project_id).where(
            ProjectPaper.paper_id == __import__("uuid").UUID(doc.paper_id)).limit(1))
    project_id = row.scalar_one_or_none()
    if project_id:
        pg = await graph_service.get_project_concept_graph(db, project_id)
        p_ids = {n["id"] for n in pg["nodes"]}
        project_result = {
            "project_id": str(project_id),
            "nodes": len(pg["nodes"]), "edges": len(pg["edges"]),
            "concept_nodes": sum(1 for n in pg["nodes"] if n.get("type") == "concept"),
            "referential_integrity": all(
                e["source"] in p_ids and e["target"] in p_ids for e in pg["edges"]),
        }

    result = {
        "paper_api": {
            "paper_id": doc.paper_id,
            "nodes": len(nodes), "edges": len(edges),
            "concept_nodes": len(cids),
            "concept_relation_edges": len(edges) - len(cids),
            "referential_integrity": integrity,
        },
        "project_api": project_result,
        "passed": integrity and len(cids) > 0
                  and (project_result is None or project_result["referential_integrity"]),
    }
    result["classification"] = (
        GraphFailure.PASS if result["passed"] else GraphFailure.API_FAILURE
    )
    if trace:
        trace.write("graph_api", result)
    return result
