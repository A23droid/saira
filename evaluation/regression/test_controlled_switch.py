"""
Controlled context-influence test using deterministic fixtures.

This is NOT the document-switch test (G–J). Those must run on real ingested
documents and are reported separately; when no genuinely conflicting question
exists between the discovered papers, they report NOT_SATISFIED rather than
substituting this.

What this does test — deterministically, on every run — is the property the
switch depends on: when the same question is asked with two different evidence
sets that give different specific answers, the generated answer must follow the
evidence it was given. The conflicting facts are known by construction, so a
failure here is unambiguous.

Marked `llm` because it calls the model. Run with:

    pytest evaluation/regression/test_controlled_switch.py -v -m llm

Skipped by default when GROQ_API_KEY is unset.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from evaluation.common.bootstrap import bootstrap, run_isolated  # noqa: E402

bootstrap()

from app.core.config import settings  # noqa: E402
from evaluation.config.evaluation_config import FIXTURES_DIR  # noqa: E402
from evaluation.grounding.causal_tests import contains_answer, looks_abstained  # noqa: E402

CORPUS = json.loads((FIXTURES_DIR / "conflicting_corpus.json").read_text(encoding="utf-8"))

requires_llm = pytest.mark.skipif(
    not settings.GROQ_API_KEY,
    reason="GROQ_API_KEY not set — LLM test skipped, not passed.",
)


def _evidence_block(doc_key: str, chunk_id: str) -> str:
    doc = CORPUS["documents"][doc_key]
    for c in doc["chunks"]:
        if c["chunk_id"] == chunk_id:
            return (f"[evidence_id={c['chunk_id']} | paper_id={doc['paper_id']} "
                    f"| page={c['page']}]\n{c['text']}")
    raise KeyError(chunk_id)


def _ask(question: str, evidence: str, scope_id: str):
    from app.services.ai_router import ai_router
    from app.services.retrieval_service import RetrievalResult, RetrievalScope

    scope = RetrievalScope("paper", scope_id, [scope_id], label="fixture")
    empty = RetrievalResult(scope=scope, query=question)

    async def run():
        return await ai_router.answer_scoped(
            scope=scope, question=question, retrieval=empty,
            history=None, evidence_override=evidence,
        )

    return run_isolated(run())


def _cases():
    return [(q, q["question"]) for q in CORPUS["questions"]]


@requires_llm
@pytest.mark.llm
@pytest.mark.parametrize("case,qid", _cases(), ids=[c[1][:40] for c in _cases()])
def test_answer_follows_document_a_then_document_b(case, qid):
    """A→answer_a then B→answer_b, with no state carried between calls.

    Each call builds a fresh scope and passes no history, so the second answer
    cannot be influenced by the first.
    """
    question = case["question"]

    a = _ask(question, _evidence_block("DOC_A", case["chunk_a"]), "fixture-doc-a")
    assert not looks_abstained(a.answer, a.abstained), (
        f"abstained despite sufficient evidence: {a.answer!r}")
    assert contains_answer(a.answer, case["answer_a"]), (
        f"A: expected {case['answer_a']!r}, got {a.answer!r}")
    assert not contains_answer(a.answer, case["answer_b"]), (
        f"A: leaked document B's value {case['answer_b']!r}: {a.answer!r}")

    b = _ask(question, _evidence_block("DOC_B", case["chunk_b"]), "fixture-doc-b")
    assert not looks_abstained(b.answer, b.abstained), (
        f"abstained despite sufficient evidence: {b.answer!r}")
    assert contains_answer(b.answer, case["answer_b"]), (
        f"B: expected {case['answer_b']!r}, got {b.answer!r}")
    assert not contains_answer(b.answer, case["answer_a"]), (
        f"B: leaked document A's value {case['answer_a']!r}: {b.answer!r}")


@requires_llm
@pytest.mark.llm
def test_reverse_order_gives_the_same_result():
    """B→answer_b then A→answer_a. Order must not change the outcome."""
    case = CORPUS["questions"][0]
    question = case["question"]

    b = _ask(question, _evidence_block("DOC_B", case["chunk_b"]), "fixture-doc-b")
    assert contains_answer(b.answer, case["answer_b"]), b.answer

    a = _ask(question, _evidence_block("DOC_A", case["chunk_a"]), "fixture-doc-a")
    assert contains_answer(a.answer, case["answer_a"]), a.answer
    assert not contains_answer(a.answer, case["answer_b"]), (
        f"reverse order leaked B's value into A's answer: {a.answer!r}")


@requires_llm
@pytest.mark.llm
def test_citations_point_at_the_supplied_fixture_chunk():
    case = CORPUS["questions"][0]
    resp = _ask(case["question"],
                _evidence_block("DOC_A", case["chunk_a"]), "fixture-doc-a")
    supplied = {e.chunk_id for e in resp.evidence} or {case["chunk_a"]}
    for c in resp.citations:
        assert c.chunk_id in supplied or c.chunk_id == case["chunk_a"], (
            f"citation {c.chunk_id!r} was not in the supplied evidence")
