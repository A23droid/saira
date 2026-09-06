"""
RAG regression tests — the invariants that must never break.

Split deliberately into two groups:

* **Pure/unit tests** run anywhere with no services. They cover the logic that
  caused real bugs (scope resolution, citation validation, evidence budgeting,
  reasoning-model handling).
* **Integration tests** need live Postgres + Neo4j and are skipped, not failed,
  when those are unavailable — so a missing service is never mistaken for a
  passing suite.

Run:  pytest evaluation/regression -v
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from evaluation.common.bootstrap import bootstrap, run_isolated  # noqa: E402

bootstrap()

from app.core.config import settings  # noqa: E402
from app.services.retrieval_service import (  # noqa: E402
    RetrievalResult, RetrievalScope, RetrievedChunk, ScopeError, retrieval_service,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def chunk(cid, pid="P1", page=1, text="x" * 100, score=0.9, idx=0):
    return RetrievedChunk(chunk_id=cid, paper_id=pid, page=page,
                          chunk_index=idx, text=text, score=score,
                          paper_title="T")


async def _services_up() -> bool:
    try:
        from app.db.neo4j_client import neo4j_client
        from app.db.session import AsyncSessionLocal
        from sqlalchemy import text
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        await neo4j_client.connect()
        s = await neo4j_client.get_session()
        async with s:
            await s.run("RETURN 1")
        return True
    except Exception:
        return False


try:
    SERVICES_UP = run_isolated(_services_up())
except Exception:
    SERVICES_UP = False

requires_services = pytest.mark.skipif(
    not SERVICES_UP, reason="Postgres/Neo4j not reachable — integration test skipped, not passed."
)


# ── 4. Embedding dimension ────────────────────────────────────────────────────

def test_embedding_dimension_is_384():
    """The Neo4j vector index is declared at 384; the model must match it."""
    from app.services.embedding_service import embedding_service
    vec = embedding_service.embed_text("scaled dot-product attention")
    assert len(vec) == 384, f"expected 384 dims, got {len(vec)}"


# ── 3/5. Chunk metadata + evidence budgeting ──────────────────────────────────

def test_evidence_block_labels_every_chunk_with_provenance():
    result = RetrievalResult(
        scope=RetrievalScope("paper", "P1", ["P1"]), query="q",
        chunks=[chunk("c1", page=3), chunk("c2", page=7)],
    )
    block, used = retrieval_service.build_evidence_block(result)
    assert len(used) == 2
    for c in used:
        assert f"evidence_id={c.chunk_id}" in block
        assert f"paper_id={c.paper_id}" in block
        assert f"page={c.page}" in block


def test_evidence_block_respects_total_budget():
    """Chunks beyond the budget must be dropped from BOTH block and used-list.

    Returning them in `used` while omitting them from the prompt would let a
    citation reference evidence the model never saw.
    """
    big = [chunk(f"c{i}", text="y" * 5000) for i in range(10)]
    result = RetrievalResult(scope=RetrievalScope("paper", "P1", ["P1"]),
                             query="q", chunks=big)
    block, used = retrieval_service.build_evidence_block(
        result, max_chunk_chars=5000, max_total_chars=12000)
    assert len(used) < len(big), "budget did not truncate"
    for c in used:
        assert c.chunk_id in block
    dropped = {c.chunk_id for c in big} - {c.chunk_id for c in used}
    for cid in dropped:
        assert f"evidence_id={cid}" not in block


def test_evidence_block_always_includes_at_least_one_chunk():
    """A single oversized chunk must still be sent, not silently dropped."""
    result = RetrievalResult(scope=RetrievalScope("paper", "P1", ["P1"]),
                             query="q", chunks=[chunk("c1", text="z" * 99999)])
    block, used = retrieval_service.build_evidence_block(
        result, max_chunk_chars=1000, max_total_chars=100)
    assert len(used) == 1 and block


# ── 1/2. Scope isolation ──────────────────────────────────────────────────────

def test_scope_carries_explicit_paper_ids():
    s = RetrievalScope("project", "PR1", ["A", "B", "C"])
    assert s.paper_ids == ["A", "B", "C"]
    assert not s.is_empty
    assert RetrievalScope("project", "PR2", []).is_empty


def test_empty_scope_returns_no_evidence():
    """An empty project must retrieve nothing rather than falling back to all."""
    scope = RetrievalScope("project", "PR-empty", [])
    result = asyncio.run(retrieval_service.retrieve(scope, "anything"))
    assert result.chunks == []
    assert result.error == "empty_scope"


def test_search_chunks_returns_nothing_for_empty_scope():
    from app.services.neo4j_service import neo4j_service
    out = asyncio.run(neo4j_service.search_chunks(None, [], [0.0] * 384, 5))
    assert out == []


# ── 6/7. Vector retrieval + empty handling (integration) ──────────────────────

@requires_services
def test_paper_scope_retrieval_is_isolated():
    """Invariant 1: retrieval scoped to paper A never returns paper B's chunks."""
    from app.db.session import AsyncSessionLocal

    async def run():
        from app.db.neo4j_client import neo4j_client
        await neo4j_client.connect()
        s = await neo4j_client.get_session()
        async with s:
            rows = await (await s.run(
                """
                MATCH (p:Paper)-[:HAS_CHUNK]->(c:Chunk)
                WHERE c.embedding IS NOT NULL
                RETURN p.id AS id, count(c) AS n ORDER BY n DESC LIMIT 2
                """)).data()
        if len(rows) < 2:
            pytest.skip("need two indexed papers")
        async with AsyncSessionLocal() as db:
            for row in rows:
                scope = await retrieval_service.resolve_paper_scope(db, row["id"])
                res = await retrieval_service.retrieve(scope, "what method is used?")
                assert res.chunks, f"no chunks for {row['id']}"
                for c in res.chunks:
                    assert c.paper_id == row["id"], (
                        f"SCOPE LEAK: chunk from {c.paper_id} in scope {row['id']}")

    run_isolated(run())


@requires_services
def test_retrieved_chunks_carry_full_metadata():
    """Invariant 3: every retrieved chunk has id, paper, page, score, text."""
    from app.db.session import AsyncSessionLocal

    async def run():
        from app.db.neo4j_client import neo4j_client
        await neo4j_client.connect()
        s = await neo4j_client.get_session()
        async with s:
            row = await (await s.run(
                """
                MATCH (p:Paper)-[:HAS_CHUNK]->(c:Chunk)
                WHERE c.embedding IS NOT NULL
                RETURN p.id AS id, count(c) AS n ORDER BY n DESC LIMIT 1
                """)).single()
        if not row:
            pytest.skip("no indexed papers")
        async with AsyncSessionLocal() as db:
            scope = await retrieval_service.resolve_paper_scope(db, row["id"])
            res = await retrieval_service.retrieve(scope, "attention mechanism")
            assert res.embedding_dim == 384
            for c in res.chunks:
                assert c.chunk_id and c.paper_id and c.text
                assert isinstance(c.score, float) and 0.0 <= c.score <= 1.0
                assert c.page is None or isinstance(c.page, int)

    run_isolated(run())


@requires_services
def test_project_scope_rejects_foreign_owner():
    """Invariant 2 + the cross-tenant leak: a project owned by someone else is 403."""
    import uuid as _uuid
    from sqlalchemy import select
    from app.db.session import AsyncSessionLocal
    from app.models.project import Project

    async def run():
        async with AsyncSessionLocal() as db:
            project = await db.scalar(select(Project).limit(1))
            if project is None:
                pytest.skip("no projects in database")
            stranger = _uuid.uuid4()
            with pytest.raises(ScopeError) as exc:
                await retrieval_service.resolve_project_scope(db, project.id, stranger)
            assert exc.value.status_code == 403

            scope = await retrieval_service.resolve_project_scope(
                db, project.id, project.user_id)
            assert scope.type == "project"

    run_isolated(run())


@requires_services
def test_project_scope_contains_only_member_papers():
    from sqlalchemy import select
    from app.db.session import AsyncSessionLocal
    from app.models.project import Project
    from app.models.project_paper import ProjectPaper

    async def run():
        async with AsyncSessionLocal() as db:
            project = await db.scalar(select(Project).limit(1))
            if project is None:
                pytest.skip("no projects")
            scope = await retrieval_service.resolve_project_scope(
                db, project.id, project.user_id)
            rows = await db.execute(
                select(ProjectPaper.paper_id).where(
                    ProjectPaper.project_id == project.id))
            expected = {str(r[0]) for r in rows}
            assert set(scope.paper_ids) == expected
            if scope.paper_ids:
                res = await retrieval_service.retrieve(scope, "method")
                for c in res.chunks:
                    assert c.paper_id in expected, "project scope leak"

    run_isolated(run())


# ── 8. Citation correctness ───────────────────────────────────────────────────

def test_fabricated_citations_are_dropped():
    """Invariant 8: a citation to evidence never supplied must not survive.

    Exercises the validator directly with a stubbed model response, so the test
    is deterministic and does not depend on the model behaving badly on cue.
    """
    from unittest.mock import AsyncMock, patch

    from app.services import ai_router as router_mod

    result = RetrievalResult(
        scope=RetrievalScope("paper", "P1", ["P1"]), query="q",
        chunks=[chunk("real-chunk-1", page=4)],
    )
    fake = {
        "answer": "The optimizer is Adam.",
        "grounded": True,
        "abstained": False,
        "citations": [
            {"evidence_id": "real-chunk-1", "claim": "optimizer"},
            {"evidence_id": "HALLUCINATED-999", "claim": "made up"},
            {"evidence_id": "", "claim": "empty"},
        ],
    }
    with patch.object(router_mod.groq_service, "chat_complete_json",
                      new=AsyncMock(return_value=fake)):
        out = asyncio.run(router_mod.answer_scoped(
            result.scope, "which optimizer?", result))

    ids = [c.chunk_id for c in out.citations]
    assert ids == ["real-chunk-1"], f"fabricated citation survived: {ids}"
    assert out.citations[0].page == 4
    assert out.citations[0].paper_id == "P1"


def test_citations_deduplicated():
    from unittest.mock import AsyncMock, patch
    from app.services import ai_router as router_mod

    result = RetrievalResult(
        scope=RetrievalScope("paper", "P1", ["P1"]), query="q",
        chunks=[chunk("c1")],
    )
    fake = {"answer": "a", "grounded": True, "abstained": False,
            "citations": [{"evidence_id": "c1", "claim": "x"},
                          {"evidence_id": "c1", "claim": "y"}]}
    with patch.object(router_mod.groq_service, "chat_complete_json",
                      new=AsyncMock(return_value=fake)):
        out = asyncio.run(router_mod.answer_scoped(result.scope, "q", result))
    assert len(out.citations) == 1


def test_answer_scoped_never_cites_outside_the_budget():
    """A chunk dropped by the context budget must not be citable."""
    from unittest.mock import AsyncMock, patch
    from app.services import ai_router as router_mod

    chunks = [chunk(f"c{i}", text="w" * 6000) for i in range(6)]
    result = RetrievalResult(scope=RetrievalScope("paper", "P1", ["P1"]),
                             query="q", chunks=chunks)
    fake = {"answer": "a", "grounded": True, "abstained": False,
            "citations": [{"evidence_id": f"c{i}", "claim": "x"} for i in range(6)]}
    with patch.object(router_mod.groq_service, "chat_complete_json",
                      new=AsyncMock(return_value=fake)):
        out = asyncio.run(router_mod.answer_scoped(result.scope, "q", result))
    supplied = {e.chunk_id for e in out.evidence}
    for c in out.citations:
        assert c.chunk_id in supplied


# ── 9/10. Context influence plumbing ──────────────────────────────────────────

def test_evidence_override_replaces_supplied_evidence():
    """Perturbation/wrong-context tests depend on the override reaching the prompt."""
    from unittest.mock import AsyncMock, patch
    from app.services import ai_router as router_mod

    result = RetrievalResult(scope=RetrievalScope("paper", "P1", ["P1"]),
                             query="q", chunks=[chunk("c1", text="Adam optimizer")])
    captured = {}

    async def capture(model, messages, **kw):
        captured["messages"] = messages
        return {"answer": "SGD", "grounded": True, "abstained": False, "citations": []}

    with patch.object(router_mod.groq_service, "chat_complete_json", new=AsyncMock(side_effect=capture)):
        asyncio.run(router_mod.answer_scoped(
            result.scope, "optimizer?", result,
            evidence_override="[evidence_id=c1 | paper_id=P1 | page=1]\nSGD optimizer"))

    joined = " ".join(m["content"] for m in captured["messages"])
    assert "SGD optimizer" in joined
    assert "Adam optimizer" not in joined


def test_no_context_produces_explicit_empty_evidence_marker():
    from unittest.mock import AsyncMock, patch
    from app.services import ai_router as router_mod

    result = RetrievalResult(scope=RetrievalScope("paper", "P1", ["P1"]),
                             query="q", chunks=[chunk("c1")])
    captured = {}

    async def capture(model, messages, **kw):
        captured["messages"] = messages
        return {"answer": "x", "grounded": False, "abstained": True, "citations": []}

    with patch.object(router_mod.groq_service, "chat_complete_json", new=AsyncMock(side_effect=capture)):
        asyncio.run(router_mod.answer_scoped(result.scope, "q", result, evidence_override=""))

    joined = " ".join(m["content"] for m in captured["messages"])
    assert "no evidence was retrieved" in joined


# ── 13. Cache / memory isolation ──────────────────────────────────────────────

def test_eval_mode_is_active_under_harness():
    assert settings.SAIRA_EVAL_MODE is True
    assert settings.SAIRA_LOG_LLM_PAYLOAD is True


def test_history_is_bounded_by_router():
    """Invariant 13: history longer than the cap is truncated before the model."""
    from unittest.mock import AsyncMock, patch
    from app.services import ai_router as router_mod

    result = RetrievalResult(scope=RetrievalScope("paper", "P1", ["P1"]),
                             query="q", chunks=[chunk("c1")])
    long_history = [{"role": "user", "content": f"m{i}"} for i in range(50)]
    captured = {}

    async def capture(model, messages, **kw):
        captured["messages"] = messages
        return {"answer": "x", "grounded": True, "abstained": False, "citations": []}

    with patch.object(router_mod.groq_service, "chat_complete_json", new=AsyncMock(side_effect=capture)):
        asyncio.run(router_mod.answer_scoped(result.scope, "q", result, history=long_history))

    roles = [m["role"] for m in captured["messages"]]
    # system + at most RAG_MAX_HISTORY_MESSAGES history + final user question
    assert len(roles) <= settings.RAG_MAX_HISTORY_MESSAGES + 2


def test_retrieval_service_holds_no_mutable_module_state():
    """No answer/retrieval cache may live at module scope in the RAG path."""
    from app.services import retrieval_service as rs
    containers = [
        name for name in dir(rs)
        if not name.startswith("__") and isinstance(getattr(rs, name), (dict, list, set))
    ]
    assert containers == [], f"module-level mutable state: {containers}"


# ── Reasoning-model handling ──────────────────────────────────────────────────

def test_empty_content_with_length_finish_reason_is_diagnosed():
    """A reasoning model that burns its budget must produce a clear error,
    not a bare 'empty response', after one bounded retry."""
    from unittest.mock import AsyncMock, MagicMock, patch
    from app.services.groq_service import GroqServiceError, groq_service

    msg = MagicMock(content="", reasoning="thinking..." * 20)
    choice = MagicMock(message=msg, finish_reason="length")
    response = MagicMock(choices=[choice])

    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=response)

    with patch.object(groq_service, "_get_client", return_value=client):
        with pytest.raises(GroqServiceError) as exc:
            asyncio.run(groq_service.chat_complete(
                "m", [{"role": "user", "content": "hi"}], max_tokens=8192))
    assert "token budget" in str(exc.value).lower()


def test_budget_retry_happens_once_then_succeeds():
    from unittest.mock import AsyncMock, MagicMock, patch
    from app.services.groq_service import groq_service

    empty = MagicMock(choices=[MagicMock(
        message=MagicMock(content="", reasoning="r"), finish_reason="length")])
    good = MagicMock(choices=[MagicMock(
        message=MagicMock(content="ok"), finish_reason="stop")])

    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=[empty, good])

    with patch.object(groq_service, "_get_client", return_value=client):
        out = asyncio.run(groq_service.chat_complete(
            "m", [{"role": "user", "content": "hi"}], max_tokens=512))
    assert out == "ok"
    assert client.chat.completions.create.await_count == 2


def test_reasoning_tags_are_stripped():
    from app.services.groq_service import clean_model_response
    assert clean_model_response("<think>secret</think>\nAnswer.") == "Answer."
    assert clean_model_response("Answer.\n<analysis>x</analysis>") == "Answer."


def test_no_context_override_makes_all_citations_invalid():
    """Under test B (no context) nothing may be cited.

    Before this was fixed, `answer_scoped` kept the original retrieval as the
    "supplied evidence" whenever an override was given, so a model citing a
    chunk it had never been shown would still validate — silently inflating
    citation accuracy in exactly the test designed to detect ungrounded answers.
    """
    from unittest.mock import AsyncMock, patch
    from app.services import ai_router as router_mod

    result = RetrievalResult(
        scope=RetrievalScope("paper", "P1", ["P1"]), query="q",
        chunks=[chunk("real-1"), chunk("real-2")],
    )
    fake = {"answer": "Adam", "grounded": True, "abstained": False,
            "citations": [{"evidence_id": "real-1", "claim": "x"},
                          {"evidence_id": "real-2", "claim": "y"}]}
    with patch.object(router_mod.groq_service, "chat_complete_json",
                      new=AsyncMock(return_value=fake)):
        out = asyncio.run(router_mod.answer_scoped(
            result.scope, "q", result, evidence_override=""))

    assert out.citations == [], "cited evidence that was never supplied"
    assert out.evidence == [], "reported evidence that was never supplied"


def test_override_derives_supplied_set_from_the_block():
    """Only chunks actually present in the override block may be cited."""
    from unittest.mock import AsyncMock, patch
    from app.services import ai_router as router_mod

    result = RetrievalResult(
        scope=RetrievalScope("paper", "P1", ["P1"]), query="q",
        chunks=[chunk("keep-1", page=2), chunk("drop-2", page=9)],
    )
    block = "[evidence_id=keep-1 | paper_id=P1 | page=2]\nsome evidence text"
    fake = {"answer": "a", "grounded": True, "abstained": False,
            "citations": [{"evidence_id": "keep-1", "claim": "x"},
                          {"evidence_id": "drop-2", "claim": "y"}]}
    with patch.object(router_mod.groq_service, "chat_complete_json",
                      new=AsyncMock(return_value=fake)):
        out = asyncio.run(router_mod.answer_scoped(
            result.scope, "q", result, evidence_override=block))

    assert [c.chunk_id for c in out.citations] == ["keep-1"]
    assert [e.chunk_id for e in out.evidence] == ["keep-1"]


def test_explicit_evidence_chunks_override_wins():
    """Wrong-context tests supply another document's chunks explicitly."""
    from unittest.mock import AsyncMock, patch
    from app.services import ai_router as router_mod

    result = RetrievalResult(scope=RetrievalScope("paper", "P1", ["P1"]),
                             query="q", chunks=[chunk("own-1")])
    foreign = [chunk("foreign-1", pid="P2", page=5)]
    block = "[evidence_id=foreign-1 | paper_id=P2 | page=5]\nunrelated text"
    fake = {"answer": "a", "grounded": True, "abstained": False,
            "citations": [{"evidence_id": "foreign-1", "claim": "x"}]}
    with patch.object(router_mod.groq_service, "chat_complete_json",
                      new=AsyncMock(return_value=fake)):
        out = asyncio.run(router_mod.answer_scoped(
            result.scope, "q", result,
            evidence_override=block, evidence_chunks=foreign))

    assert [c.chunk_id for c in out.citations] == ["foreign-1"]
    assert out.citations[0].paper_id == "P2"
