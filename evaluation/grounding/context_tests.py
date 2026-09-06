"""
Document-switch tests (G–J).

A document switch is only meaningful when the SAME question has a specific but
DIFFERENT answer in each of the two documents. The common shortcut — document A
answers, document B abstains — demonstrates nothing beyond retrieval finding
something in one place and not the other, so it is explicitly rejected here.

Finding a genuinely conflicting question is done by inspecting both documents'
real chunks and asking for a question each answers differently, then verifying
both claimed answers actually appear in their respective sources. If no such
question can be constructed, the test reports NOT_SATISFIED. That is an honest
outcome; fabricating a conflict would make the whole evaluation meaningless.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from evaluation.config.evaluation_config import RagFailure
from evaluation.grounding.causal_tests import contains_answer, looks_abstained, normalize

logger = logging.getLogger(__name__)

_CONFLICT_SYSTEM = (
    "You are constructing a controlled experiment. You are given excerpts from "
    "TWO different scientific papers, A and B.\n"
    "Find ONE question that BOTH papers answer, but with DIFFERENT specific "
    "answers (e.g. a different optimizer, dataset, metric, layer count, "
    "accuracy).\n"
    "Both answers must appear VERBATIM in the respective excerpts.\n"
    "If no such question exists, return {\"found\": false}. Do NOT invent one — "
    "returning false is the correct answer when the papers do not conflict.\n"
    'Return JSON: {"found": true, "question": "...", "answer_a": "...", '
    '"answer_b": "..."}'
)


async def find_conflicting_question(
    doc_a, doc_b, max_chars: int = 9000, trace=None
) -> Optional[Dict[str, Any]]:
    """Search for a question the two documents answer differently."""
    from app.schemas.ai import AITask
    from app.services.ai_router import _model_for
    from app.services.groq_service import groq_service
    from evaluation.retrieval.retrieval_evaluation import fetch_chunks

    a_chunks = await fetch_chunks(doc_a.paper_id, limit=14)
    b_chunks = await fetch_chunks(doc_b.paper_id, limit=14)
    if not a_chunks or not b_chunks:
        return None

    def joined(chunks):
        out, used = [], 0
        for c in chunks:
            t = (c["text"] or "")[:1400]
            if used + len(t) > max_chars:
                break
            out.append(t)
            used += len(t)
        return "\n---\n".join(out)

    a_text, b_text = joined(a_chunks), joined(b_chunks)

    try:
        data = await groq_service.chat_complete_json(
            _model_for(AITask.LIT_REVIEW_SYNTHESIS),
            [
                {"role": "system", "content": _CONFLICT_SYSTEM},
                {"role": "user", "content":
                    f"PAPER A: {doc_a.title}\n{a_text}\n\n"
                    f"=====\n\nPAPER B: {doc_b.title}\n{b_text}\n\nReturn JSON."},
            ],
            temperature=0.1, max_tokens=2048,
        )
    except Exception as exc:
        logger.error("Conflict search failed: %s", exc)
        return None

    if not data.get("found"):
        return None

    question = str(data.get("question") or "").strip()
    ans_a = str(data.get("answer_a") or "").strip()
    ans_b = str(data.get("answer_b") or "").strip()
    if not (question and ans_a and ans_b):
        return None

    # Reject a "conflict" whose two answers are effectively the same.
    if normalize(ans_a) == normalize(ans_b):
        logger.info("Rejected conflict: identical answers.")
        return None
    # Both answers must be verifiable in their own source text.
    if not contains_answer(a_text, ans_a) or not contains_answer(b_text, ans_b):
        logger.info("Rejected conflict: an answer is not present in its source.")
        return None

    candidate = {
        "question": question, "answer_a": ans_a, "answer_b": ans_b,
        "paper_a": doc_a.paper_id, "paper_b": doc_b.paper_id,
    }
    if trace:
        trace.write("conflict_candidate", candidate)
    return candidate


async def run_document_switch(
    db, doc_a, doc_b, conflict: Dict[str, Any], trace=None
) -> List[Dict[str, Any]]:
    """Run G→H then, with state cleared, I→J in reverse order.

    Each call constructs its scope and retrieval from scratch and passes no
    conversation history, so nothing survives between runs. The reverse order
    exists to catch order-dependent contamination that a single A→B sequence
    would hide.
    """
    from app.services.ai_router import ai_router
    from app.services.retrieval_service import retrieval_service

    q = conflict["question"]

    async def ask(doc, expected, other_expected, label):
        scope = await retrieval_service.resolve_paper_scope(db, doc.paper_id)
        retrieval = await retrieval_service.retrieve(scope, q)
        resp = await ai_router.answer_scoped(
            scope=scope, question=q, retrieval=retrieval, history=None)
        got_own = contains_answer(resp.answer, expected)
        got_other = contains_answer(resp.answer, other_expected)
        abstained = looks_abstained(resp.answer, resp.abstained)

        if got_own and not got_other:
            verdict, passed = RagFailure.PASS, True
        elif got_other:
            # Answered with the *other* document's value while scoped here.
            verdict, passed = RagFailure.PRIOR_KNOWLEDGE_OR_LEAKAGE, False
        elif abstained:
            # An abstention is not a document switch; it is a retrieval or
            # generation shortfall, and must not be scored as success.
            verdict, passed = RagFailure.RETRIEVAL_FAILURE, False
        else:
            verdict, passed = RagFailure.GROUNDING_FAILURE, False

        rec = {
            "test": label,
            "question": q,
            "expected": expected,
            "other_document_answer": other_expected,
            "actual": resp.answer,
            "abstained": abstained,
            "matched_own_document": got_own,
            "matched_other_document": got_other,
            "scope_paper_id": doc.paper_id,
            "retrieved_chunk_ids": [e.chunk_id for e in resp.evidence],
            "retrieved_paper_ids": sorted({e.paper_id for e in resp.evidence}),
            "citations": [c.model_dump() for c in resp.citations],
            "prompt_chars": resp.prompt_chars,
            "passed": passed,
            "verdict": verdict,
        }
        if trace:
            trace.write("document_switch", rec)
        return rec

    results = [
        await ask(doc_a, conflict["answer_a"], conflict["answer_b"], "G_documentA_to_answerA"),
        await ask(doc_b, conflict["answer_b"], conflict["answer_a"], "H_documentB_to_answerB"),
        # State is clean by construction (new scope, new retrieval, no history).
        await ask(doc_b, conflict["answer_b"], conflict["answer_a"], "I_reverse_documentB_to_answerB"),
        await ask(doc_a, conflict["answer_a"], conflict["answer_b"], "J_reverse_documentA_to_answerA"),
    ]
    return results


def not_satisfied_records(reason: str) -> List[Dict[str, Any]]:
    """Explicit NOT_SATISFIED records when no genuine conflict was found."""
    return [
        {
            "test": name,
            "passed": None,
            "verdict": "NOT_SATISFIED",
            "reason": reason,
            "note": "No question was found that both documents answer with "
                    "different specific values. Reporting this rather than "
                    "substituting an answer/abstain pair, which would not "
                    "demonstrate a document switch.",
        }
        for name in (
            "G_documentA_to_answerA", "H_documentB_to_answerB",
            "I_reverse_documentB_to_answerB", "J_reverse_documentA_to_answerA",
        )
    ]
