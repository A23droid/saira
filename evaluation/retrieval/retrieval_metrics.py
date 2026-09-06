"""
Standard retrieval metrics.

`relevant` is the set of chunk IDs that genuinely contain the answer. In this
harness that set is established by construction: each question is generated
*from* a specific chunk, so the gold chunk is known before retrieval runs. That
avoids grading retrieval against a judgement made after seeing its output.
"""

from __future__ import annotations

from statistics import mean
from typing import Dict, Iterable, List, Optional, Sequence


def hit_at_k(retrieved: Sequence[str], relevant: Iterable[str], k: int) -> int:
    rel = set(relevant)
    return int(any(c in rel for c in list(retrieved)[:k]))


def recall_at_k(retrieved: Sequence[str], relevant: Iterable[str], k: int) -> float:
    rel = set(relevant)
    if not rel:
        return 0.0
    found = sum(1 for c in set(list(retrieved)[:k]) if c in rel)
    return found / len(rel)


def reciprocal_rank(retrieved: Sequence[str], relevant: Iterable[str]) -> float:
    rel = set(relevant)
    for i, c in enumerate(retrieved, start=1):
        if c in rel:
            return 1.0 / i
    return 0.0


def precision_at_k(retrieved: Sequence[str], relevant: Iterable[str], k: int) -> float:
    rel = set(relevant)
    top = list(retrieved)[:k]
    if not top:
        return 0.0
    return sum(1 for c in top if c in rel) / len(top)


def aggregate(records: List[Dict], k_values: Sequence[int]) -> Dict[str, float]:
    """Aggregate per-question records into a metrics block.

    A record needs `retrieved_chunk_ids` and `relevant_chunk_ids`. Questions
    with no gold chunk are excluded from accuracy metrics and counted
    separately, so an unanswerable question cannot silently inflate or deflate
    the score.
    """
    scored = [r for r in records if r.get("relevant_chunk_ids")]
    out: Dict[str, float] = {
        "questions_total": len(records),
        "questions_scored": len(scored),
        "questions_unscored": len(records) - len(scored),
    }
    if not scored:
        return out

    for k in k_values:
        out[f"hit@{k}"] = mean(
            hit_at_k(r["retrieved_chunk_ids"], r["relevant_chunk_ids"], k) for r in scored
        )
        out[f"recall@{k}"] = mean(
            recall_at_k(r["retrieved_chunk_ids"], r["relevant_chunk_ids"], k) for r in scored
        )
        out[f"precision@{k}"] = mean(
            precision_at_k(r["retrieved_chunk_ids"], r["relevant_chunk_ids"], k) for r in scored
        )
    out["mrr"] = mean(
        reciprocal_rank(r["retrieved_chunk_ids"], r["relevant_chunk_ids"]) for r in scored
    )

    lat = [r["latency_ms"] for r in records if r.get("latency_ms") is not None]
    if lat:
        ordered = sorted(lat)
        out["latency_ms_mean"] = mean(lat)
        out["latency_ms_p50"] = ordered[len(ordered) // 2]
        out["latency_ms_max"] = ordered[-1]

    scores = [s for r in records for s in (r.get("similarity_scores") or [])]
    if scores:
        out["similarity_mean"] = mean(scores)
        out["similarity_max"] = max(scores)
        out["similarity_min"] = min(scores)

    cands = [r["candidate_count"] for r in records if r.get("candidate_count") is not None]
    if cands:
        out["candidates_mean"] = mean(cands)

    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in out.items()}
