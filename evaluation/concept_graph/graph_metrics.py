"""Concept-graph metrics computed from the live Neo4j graph."""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional

from evaluation.config.evaluation_config import GraphFailure


async def paper_graph_metrics(neo_session, paper_id: str) -> Dict[str, Any]:
    from app.services.neo4j_service import neo4j_service

    data = await neo4j_service.get_paper_concept_graph(neo_session, paper_id)
    concepts = data.get("concepts", [])
    relations = data.get("relations", [])

    with_pages = sum(1 for c in concepts if c.get("pages"))
    with_chunks = sum(1 for c in concepts if c.get("chunk_ids"))
    with_evidence = sum(1 for c in concepts if c.get("evidence"))

    names = [c.get("name") or "" for c in concepts]
    canon = Counter()
    try:
        from app.services.concept_service import canonical_key
        canon = Counter(canonical_key(n) for n in names)
    except Exception:
        pass
    dup_after_norm = sum(v - 1 for v in canon.values() if v > 1)

    concept_ids = {c["id"] for c in concepts}
    dangling = [r for r in relations
                if r["source"] not in concept_ids or r["target"] not in concept_ids]
    connected = {r["source"] for r in relations} | {r["target"] for r in relations}
    orphan_nodes = [c["id"] for c in concepts if c["id"] not in connected]

    return {
        "paper_id": paper_id,
        "concept_count": len(concepts),
        "unique_concept_names": len(set(names)),
        "relation_count": len(relations),
        "relation_types": dict(Counter(r.get("type") for r in relations)),
        "duplicate_after_normalization": dup_after_norm,
        "provenance_pages": with_pages,
        "provenance_chunks": with_chunks,
        "provenance_evidence": with_evidence,
        "provenance_coverage_chunks": round(with_chunks / len(concepts), 4) if concepts else None,
        "provenance_coverage_evidence": round(with_evidence / len(concepts), 4) if concepts else None,
        "dangling_relations": len(dangling),
        "orphan_concept_nodes_in_paper_view": len(orphan_nodes),
        "sample_concepts": [
            {"name": c.get("name"), "importance": c.get("importance"),
             "pages": c.get("pages"), "chunks": len(c.get("chunk_ids") or [])}
            for c in concepts[:8]
        ],
        "sample_relations": [
            {"source": next((c["name"] for c in concepts if c["id"] == r["source"]), "?"),
             "type": r.get("type"),
             "target": next((c["name"] for c in concepts if c["id"] == r["target"]), "?")}
            for r in relations[:8]
        ],
    }


def classify_graph(metrics: Dict[str, Any]) -> List[str]:
    """Failure classification for one paper's graph — never a single bucket."""
    failures: List[str] = []
    if metrics["concept_count"] == 0:
        failures.append(GraphFailure.EXTRACTION_FAILURE)
    if metrics["duplicate_after_normalization"] > 0:
        failures.append(GraphFailure.NORMALIZATION_FAILURE)
    if metrics["concept_count"] > 2 and metrics["relation_count"] == 0:
        failures.append(GraphFailure.RELATIONSHIP_FAILURE)
    if metrics["dangling_relations"] > 0:
        failures.append(GraphFailure.RELATIONSHIP_FAILURE)
    cov = metrics.get("provenance_coverage_evidence")
    if cov is not None and cov < 0.5:
        failures.append(GraphFailure.PROVENANCE_FAILURE)
    return failures or [GraphFailure.PASS]


def graph_verdict(per_paper: List[Dict[str, Any]], isolation_ok: bool,
                  idempotent: bool, api_ok: bool,
                  extraction_reports: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Conservative overall verdict for the concept graph."""
    extracted = [m for m in per_paper if m["concept_count"] > 0]
    related = [m for m in per_paper if m["relation_count"] > 0]
    with_prov = [m for m in per_paper
                 if (m.get("provenance_coverage_evidence") or 0) >= 0.5]

    reasons: List[str] = []
    # Concepts measured in Neo4j may predate this run. If extraction failed
    # now, say so rather than crediting leftover data as a success.
    failed_now = [r for r in (extraction_reports or []) if not r.get('ok')]
    if failed_now:
        reasons.append(
            f"{len(failed_now)} extraction(s) failed during this run: "
            + "; ".join(sorted({str(r.get('error')) for r in failed_now}))
        )
    if not extracted:
        reasons.append("no concepts extracted for any evaluated paper")
    if len(related) < len(per_paper):
        reasons.append(f"{len(per_paper) - len(related)} paper(s) produced no relations")
    if len(with_prov) < len(per_paper):
        reasons.append(f"{len(per_paper) - len(with_prov)} paper(s) below 50% evidence provenance")
    if not isolation_ok:
        reasons.append("graph isolation violated")
    if not idempotent:
        reasons.append("re-ingestion is not idempotent")
    if not api_ok:
        reasons.append("graph API did not return the expected structure")

    if not extracted or not isolation_ok or not api_ok:
        verdict = "NOT FUNCTIONAL"
    elif reasons:
        verdict = "PARTIALLY FUNCTIONAL"
    else:
        verdict = "FUNCTIONAL"

    return {
        "verdict": verdict,
        "papers_evaluated": len(per_paper),
        "papers_with_concepts": len(extracted),
        "papers_with_relations": len(related),
        "papers_with_provenance": len(with_prov),
        "isolation_ok": isolation_ok,
        "reingestion_idempotent": idempotent,
        "api_ok": api_ok,
        "extractions_failed_this_run": len(failed_now),
        "limiting_factors": reasons,
    }
