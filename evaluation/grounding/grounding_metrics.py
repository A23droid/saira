"""
Answer / grounding metrics.

The central rule: groundedness is never inferred from correctness. A correct
answer counts as *grounded* only when the evidence that supports it was
actually retrieved and cited, and only when the causal tests show the answer
tracking the evidence.
"""

from __future__ import annotations

from collections import Counter
from statistics import mean
from typing import Any, Dict, List


def summarize_causal(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_test: Dict[str, Dict[str, Any]] = {}
    for r in records:
        b = by_test.setdefault(r["test"], {"total": 0, "passed": 0, "failed": 0,
                                           "not_applicable": 0, "verdicts": Counter()})
        b["total"] += 1
        b["verdicts"][r.get("verdict", "UNKNOWN")] += 1
        if r.get("passed") is True:
            b["passed"] += 1
        elif r.get("passed") is False:
            b["failed"] += 1
        else:
            b["not_applicable"] += 1
    for b in by_test.values():
        b["verdicts"] = dict(b["verdicts"])
        scored = b["passed"] + b["failed"]
        b["pass_rate"] = round(b["passed"] / scored, 4) if scored else None
    return by_test


def citation_metrics(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Citation accuracy = does each citation point at evidence really supplied?

    `answer_scoped` already drops citations that do not match supplied
    evidence, so a non-zero count here would indicate the validator regressed.
    Both numbers are reported rather than assumed.
    """
    total = valid = answers_with = answers_without = 0
    for r in records:
        cits = r.get("citations") or []
        if not isinstance(cits, list):
            # A malformed record must not abort reporting for the whole run.
            cits = []
        supplied = set(r.get("evidence_chunk_ids") or [])
        if cits:
            answers_with += 1
        elif r.get("abstained") is False:
            answers_without += 1
        for c in cits:
            total += 1
            if c.get("chunk_id") and c["chunk_id"] in supplied:
                valid += 1
    return {
        "citations_total": total,
        "citations_traceable_to_evidence": valid,
        "citation_accuracy": round(valid / total, 4) if total else None,
        "answers_with_citations": answers_with,
        "non_abstained_answers_without_citations": answers_without,
        "fabricated_citations": total - valid,
    }


def context_influence(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """How strongly the answer follows the supplied evidence.

    Measured only from the perturbation test, where the evidence was
    deliberately changed and the correct behaviour is to follow it.
    """
    d = [r for r in records if r["test"] == "D_perturbed_context"
         and r.get("verdict") != "NOT_APPLICABLE"]
    if not d:
        return {"applicable": 0, "followed_perturbation_rate": None}
    followed = sum(1 for r in d if r.get("followed_perturbation"))
    return {
        "applicable": len(d),
        "followed_perturbation": followed,
        "kept_original_value": sum(1 for r in d if r.get("kept_original_value")),
        "followed_perturbation_rate": round(followed / len(d), 4),
    }


def leakage_signals(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Cases where an answer appeared without supporting evidence."""
    b = [r for r in records if r["test"] == "B_no_context"]
    c = [r for r in records if r["test"] == "C_wrong_context"]
    return {
        "no_context_total": len(b),
        "no_context_correct_abstentions": sum(
            1 for r in b if r.get("verdict") == "CORRECT_ABSTENTION"),
        "no_context_answered_from_prior_knowledge": sum(
            1 for r in b if r.get("answered_correctly_without_evidence")),
        "wrong_context_total": len(c),
        "wrong_context_coincidental_overlap": sum(
            1 for r in c if r.get("coincidental_overlap")),
        "wrong_context_answered_target_anyway": sum(
            1 for r in c if r.get("answered_target_anyway") and not r.get("coincidental_overlap")),
    }


def overall_verdict(causal: Dict[str, Any], switch: List[Dict[str, Any]],
                    influence: Dict[str, Any], leakage: Dict[str, Any]) -> Dict[str, Any]:
    """Conservative verdict for the RAG pipeline.

    STRONGLY VERIFIED requires all of:
      * correct-context answers largely succeed,
      * no-context predominantly abstains,
      * perturbed evidence changes the answer,
      * a genuine conflicting document switch works in both orders.
    Anything less is PARTIALLY VERIFIED or NOT VERIFIED. The wording is
    deliberately experimental: this is evidence of causal grounding, not proof
    that the model lacks prior knowledge.
    """
    a = causal.get("A_correct_context", {})
    b = causal.get("B_no_context", {})
    a_rate = a.get("pass_rate")
    b_abst = (b.get("verdicts", {}).get("CORRECT_ABSTENTION", 0) / b["total"]) if b.get("total") else None
    d_rate = influence.get("followed_perturbation_rate")

    switch_scored = [r for r in switch if r.get("passed") is not None]
    switch_ok = bool(switch_scored) and all(r.get("passed") for r in switch_scored)
    switch_attempted = bool(switch_scored)

    reasons: List[str] = []
    if a_rate is not None and a_rate < 0.6:
        reasons.append(f"correct-context pass rate {a_rate:.0%} below 60%")
    if b_abst is not None and b_abst < 0.6:
        reasons.append(f"no-context abstention rate {b_abst:.0%} below 60%")
    if d_rate is not None and d_rate < 0.6:
        reasons.append(f"perturbation-following rate {d_rate:.0%} below 60%")
    if not switch_attempted:
        reasons.append("no genuine conflicting document switch could be constructed")
    elif not switch_ok:
        reasons.append("document-switch test did not pass in both orders")

    if not reasons:
        verdict = "STRONGLY VERIFIED RAG"
    elif (a_rate or 0) >= 0.6 and (d_rate is None or d_rate >= 0.5):
        verdict = "PARTIALLY VERIFIED"
    else:
        verdict = "NOT VERIFIED"

    return {
        "verdict": verdict,
        "correct_context_pass_rate": a_rate,
        "no_context_abstention_rate": round(b_abst, 4) if b_abst is not None else None,
        "perturbation_follow_rate": d_rate,
        "document_switch_attempted": switch_attempted,
        "document_switch_all_passed": switch_ok,
        "limiting_factors": reasons,
        "interpretation": (
            "These results are experimental evidence of causal document "
            "grounding, not proof that the model has no prior knowledge of "
            "these papers."
        ),
    }
