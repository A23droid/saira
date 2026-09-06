"""
Causal grounding tests (A–J).

The question these answer is not "is the answer correct?" but "did the supplied
evidence *cause* the answer?" A correct answer proves nothing on its own: the
model may know the paper. So each test manipulates the evidence and observes
whether the answer moves with it.

Tests:
    A  Correct context          evidence supports the answer
    B  No context               evidence removed
    C  Wrong context            evidence from an unrelated document
    D  Perturbed context        a fact in the evidence is deliberately altered
    E  Summary only             abstract/metadata only, no retrieved chunks
    F  Retrieved chunks only    chunks with no metadata (the production path)
    G  Document A → Answer A    conflicting-fact switch
    H  Document B → Answer B
    I  Document B → Answer B    replayed in reverse order, clean state
    J  Document A → Answer A

Interpretation rules enforced in code, not in prose:
  * An abstention under no-context is CORRECT behaviour, not a failure.
  * A correct answer under *no* context is evidence of prior knowledge or
    leakage — it is recorded as such, never as a pass.
  * If wrong context happens to contain the target value, the case is marked
    TEST_ARTIFACT rather than counted as grounding.
  * A document switch only counts when BOTH documents produce a specific,
    different, non-abstained answer.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from evaluation.config.evaluation_config import RagFailure

logger = logging.getLogger(__name__)


# ── Answer comparison ─────────────────────────────────────────────────────────

_ABSTAIN_MARKERS = (
    "not available", "does not contain", "no evidence", "cannot be determined",
    "not provided", "insufficient", "not stated", "not mentioned",
    "unable to answer", "no information", "not specified", "does not provide",
    "not present in", "no retrieved evidence",
)


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", (text or "").lower()).strip()


def looks_abstained(answer: str, flag: bool) -> bool:
    if flag:
        return True
    low = (answer or "").lower()
    return any(m in low for m in _ABSTAIN_MARKERS)


def contains_answer(answer: str, expected: str) -> bool:
    """Loose containment check for a short expected value.

    Deliberately permissive on formatting (case, punctuation) and strict on
    content: the expected token sequence must appear. For multi-word expected
    answers, a majority of the distinctive tokens must be present, which avoids
    both false negatives from rewording and false positives from one shared
    stopword.
    """
    a, e = normalize(answer), normalize(expected)
    if not a or not e:
        return False
    if e in a:
        return True
    tokens = [t for t in e.split() if len(t) > 2]
    if not tokens:
        return False
    hits = sum(1 for t in tokens if t in a)
    return hits >= max(1, int(len(tokens) * 0.7))


# ── Evidence builders ─────────────────────────────────────────────────────────

def evidence_from_chunks(chunks) -> str:
    return "\n\n".join(
        f"[evidence_id={c.chunk_id} | paper_id={c.paper_id} | page={c.page}]\n{c.text[:2000]}"
        for c in chunks
    )


def apply_perturbation(text: str, perturbations: List[Dict[str, str]]) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Alter one fact in the evidence, reporting exactly what changed.

    Returns (text, applied) where `applied` is None if no perturbation token was
    present — in that case the test must be reported as not-applicable rather
    than as a pass, since nothing was actually changed.
    """
    for p in perturbations:
        src, dst = p["from"], p["to"]
        if re.search(rf"\b{re.escape(src)}\b", text):
            new_text, n = re.subn(rf"\b{re.escape(src)}\b", dst, text)
            return new_text, {"from": src, "to": dst, "occurrences": n}
    return text, None


# ── Test runner ───────────────────────────────────────────────────────────────

class CausalTestRunner:

    def __init__(self, db, config, trace=None):
        self.db = db
        self.config = config
        self.trace = trace

    async def _answer(self, scope, question, retrieval,
                      evidence_override=None, evidence_chunks=None):
        from app.services.ai_router import ai_router
        return await ai_router.answer_scoped(
            scope=scope, question=question, retrieval=retrieval,
            history=None,                      # no history: no cross-turn leakage
            evidence_override=evidence_override,
            # Wrong-context evidence comes from another document, so the chunks
            # backing it must be passed explicitly — they are not in this
            # scope's retrieval and could not be derived from it.
            evidence_chunks=evidence_chunks,
            include_evidence_text=False,
        )

    async def run_for_fact(
        self, document, fact: Dict[str, Any], wrong_document
    ) -> List[Dict[str, Any]]:
        """Run tests A–F for one question."""
        from app.services.retrieval_service import retrieval_service

        question, expected = fact["question"], fact["answer"]
        scope = await retrieval_service.resolve_paper_scope(self.db, document.paper_id)
        retrieval = await retrieval_service.retrieve(scope, question)
        results: List[Dict[str, Any]] = []

        # -- A. Correct context ------------------------------------------------
        block, used = retrieval_service.build_evidence_block(retrieval)
        gold_retrieved = fact["gold_chunk_id"] in {c.chunk_id for c in used}
        a = await self._answer(scope, question, retrieval)
        a_ok = contains_answer(a.answer, expected)
        a_abst = looks_abstained(a.answer, a.abstained)

        if a_ok and not a_abst:
            verdict = RagFailure.PASS
        elif not gold_retrieved:
            # The evidence containing the answer never reached the model, so
            # this is a retrieval problem, not a generation or grounding one.
            verdict = RagFailure.RETRIEVAL_FAILURE
        elif a_abst:
            verdict = RagFailure.GENERATION_FAILURE
        else:
            verdict = RagFailure.GROUNDING_FAILURE

        results.append(self._record(
            "A_correct_context", question, expected, a,
            expectation="answer matches expected value",
            passed=(verdict == RagFailure.PASS), verdict=verdict,
            extra={"gold_chunk_retrieved": gold_retrieved,
                   "gold_chunk_id": fact["gold_chunk_id"],
                   "evidence_chars": len(block)},
        ))

        # -- B. No context -----------------------------------------------------
        b = await self._answer(scope, question, retrieval, evidence_override="")
        b_ok = contains_answer(b.answer, expected)
        b_abst = looks_abstained(b.answer, b.abstained)
        if b_abst and not b_ok:
            b_verdict, b_pass = RagFailure.CORRECT_ABSTENTION, True
        elif b_ok:
            # Right answer with no evidence at all: the model already knew it.
            b_verdict, b_pass = RagFailure.PRIOR_KNOWLEDGE_OR_LEAKAGE, False
        else:
            b_verdict, b_pass = RagFailure.GROUNDING_FAILURE, False
        results.append(self._record(
            "B_no_context", question, expected, b,
            expectation="abstain (no evidence supplied)",
            passed=b_pass, verdict=b_verdict,
            extra={"answered_correctly_without_evidence": b_ok},
        ))

        # -- C. Wrong context --------------------------------------------------
        wrong_block = ""
        w_used: List[Any] = []
        overlap = False
        if wrong_document is not None:
            w_scope = await retrieval_service.resolve_paper_scope(
                self.db, wrong_document.paper_id)
            w_ret = await retrieval_service.retrieve(w_scope, question)
            wrong_block, w_used = retrieval_service.build_evidence_block(w_ret)
            # If the unrelated evidence happens to contain the target value,
            # a "correct" answer here is coincidence, not grounding.
            overlap = contains_answer(wrong_block, expected)

        c = await self._answer(scope, question, retrieval,
                               evidence_override=wrong_block,
                               evidence_chunks=w_used)
        c_ok = contains_answer(c.answer, expected)
        c_abst = looks_abstained(c.answer, c.abstained)
        if overlap:
            c_verdict, c_pass = RagFailure.TEST_ARTIFACT, False
        elif c_abst or not c_ok:
            c_verdict, c_pass = RagFailure.CORRECT_ABSTENTION, True
        else:
            c_verdict, c_pass = RagFailure.PRIOR_KNOWLEDGE_OR_LEAKAGE, False
        results.append(self._record(
            "C_wrong_context", question, expected, c,
            expectation="abstain or avoid the target value (evidence is unrelated)",
            passed=c_pass, verdict=c_verdict,
            extra={"wrong_doc": getattr(wrong_document, "paper_id", None),
                   "coincidental_overlap": overlap,
                   "answered_target_anyway": c_ok},
        ))

        # -- D. Perturbed context ---------------------------------------------
        perturbed, applied = apply_perturbation(block, self.config.perturbations)
        if applied is None:
            results.append(self._record(
                "D_perturbed_context", question, expected, None,
                expectation="answer follows the altered evidence",
                passed=None, verdict="NOT_APPLICABLE",
                extra={"reason": "no perturbation token present in evidence"},
            ))
        else:
            d = await self._answer(scope, question, retrieval, evidence_override=perturbed)
            followed = contains_answer(d.answer, applied["to"])
            kept_old = contains_answer(d.answer, applied["from"])
            if followed and not kept_old:
                d_verdict, d_pass = RagFailure.PASS, True
            elif kept_old:
                d_verdict, d_pass = RagFailure.CONTEXT_INFLUENCE_FAILURE, False
            else:
                d_verdict, d_pass = RagFailure.CONTEXT_INFLUENCE_FAILURE, False
            results.append(self._record(
                "D_perturbed_context", question, expected, d,
                expectation=f"answer reflects '{applied['to']}' (was '{applied['from']}')",
                passed=d_pass, verdict=d_verdict,
                extra={"perturbation": applied,
                       "followed_perturbation": followed,
                       "kept_original_value": kept_old},
            ))

        # -- E. Summary only ---------------------------------------------------
        from sqlalchemy import select
        from app.models.paper import Paper
        paper = await self.db.scalar(
            select(Paper).where(Paper.id == __import__("uuid").UUID(document.paper_id)))
        summary_block = (
            f"[evidence_id=summary_{document.paper_id} | paper_id={document.paper_id} | page=n/a]\n"
            f"Title: {paper.title}\nAbstract: {paper.abstract or '(none)'}"
        )
        e = await self._answer(scope, question, retrieval,
                               evidence_override=summary_block,
                               evidence_chunks=[])
        e_ok = contains_answer(e.answer, expected)
        e_abst = looks_abstained(e.answer, e.abstained)
        in_summary = contains_answer(summary_block, expected)
        results.append(self._record(
            "E_summary_only", question, expected, e,
            expectation="abstain unless the abstract genuinely contains the fact",
            passed=(e_ok if in_summary else (e_abst or not e_ok)),
            verdict=(RagFailure.PASS if (e_ok if in_summary else (e_abst or not e_ok))
                     else RagFailure.PRIOR_KNOWLEDGE_OR_LEAKAGE),
            extra={"fact_present_in_summary": in_summary, "answered": e_ok},
        ))

        # -- F. Retrieved chunks only (production path) ------------------------
        results.append(self._record(
            "F_retrieved_chunks_only", question, expected, a,
            expectation="same as A — the production path supplies chunks only",
            passed=(verdict == RagFailure.PASS), verdict=verdict,
            extra={"note": "identical to A by construction: the production "
                           "prompt contains retrieved chunks and no summary",
                   # NB: must not be named "citations" — `extra` is splatted
                   # last and would overwrite the citations list with an int.
                   "citation_count": len(a.citations)},
        ))

        return results

    def _record(self, test, question, expected, answer_obj, expectation,
                passed, verdict, extra=None) -> Dict[str, Any]:
        rec = {
            "test": test,
            "question": question,
            "expected": expected,
            "expectation": expectation,
            "actual": (answer_obj.answer if answer_obj else None),
            "abstained": (bool(answer_obj.abstained) if answer_obj else None),
            "grounded_flag": (bool(answer_obj.grounded) if answer_obj else None),
            "citations": ([c.model_dump() for c in answer_obj.citations]
                          if answer_obj else []),
            "evidence_chunk_ids": ([e.chunk_id for e in answer_obj.evidence]
                                   if answer_obj else []),
            "prompt_chars": (answer_obj.prompt_chars if answer_obj else 0),
            "passed": passed,
            "verdict": verdict,
            **(extra or {}),
        }
        if self.trace:
            self.trace.write("causal_test", rec)
        return rec
