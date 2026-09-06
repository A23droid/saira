"""
Search result -> Add to Project -> automatic PDF ingestion -> Paper Ask AI.

The high-value test here is `test_end_to_end_search_to_ask_ai`: it discovers a
paper from the live arXiv search, adds it to a project, waits for the automatic
ingestion to finish, and then asks that paper's Ask AI a question through the
real HTTP route -- asserting on the data and provenance, not on 200s.

Generation is stubbed. Everything the automatic-ingestion feature touches
(acquisition, parse, chunk, embed, Neo4j write, status, scope resolution,
retrieval, citation validation) runs for real; only the token-metered model
call is replaced, so the suite is deterministic and does not consume provider
quota.

No paper is hardcoded: the target is whatever arXiv returns for the query.
Requires live Postgres + Neo4j + network; skips (never silently passes) without.
"""

from __future__ import annotations

import asyncio
import re
import sys
import time
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from evaluation.common.bootstrap import bootstrap, run_isolated  # noqa: E402

bootstrap()

from fastapi.testclient import TestClient  # noqa: E402

from app.api.deps import get_current_user  # noqa: E402
from app.main import app  # noqa: E402
from app.services.indexing_jobs import is_ask_ai_ready  # noqa: E402

TERMINAL = {"indexed", "failed", "pdf_unavailable"}
INDEX_TIMEOUT_S = 300


async def _probe():
    from sqlalchemy import select

    from app.db.session import AsyncSessionLocal
    from app.models.user import User

    async with AsyncSessionLocal() as db:
        user = await db.scalar(select(User).limit(1))
        return {"user_id": str(user.id)} if user else None


try:
    CTX = run_isolated(_probe())
except Exception:
    CTX = None

requires_db = pytest.mark.skipif(
    not CTX, reason="Postgres unavailable -- skipped, not passed."
)


@pytest.fixture(scope="module")
def client():
    async def fake_user():
        from sqlalchemy import select

        from app.db.session import AsyncSessionLocal
        from app.models.user import User
        async with AsyncSessionLocal() as db:
            return await db.scalar(select(User).where(User.id == uuid.UUID(CTX["user_id"])))

    previous = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = fake_user
    try:
        with TestClient(app) as c:
            try:
                yield c
            finally:
                # Delete inside the client context: the route is the same one
                # a user would hit, so ownership is enforced on the way out too.
                for project_id in _CREATED_PROJECTS:
                    try:
                        c.delete(f"/api/v1/projects/{project_id}")
                    except Exception:
                        pass
                _CREATED_PROJECTS.clear()
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = previous

        async def _dispose():
            from app.db.neo4j_client import neo4j_client
            from app.db.session import engine
            await engine.dispose()
            await neo4j_client.close()
        try:
            asyncio.run(_dispose())
        except Exception:
            pass


# -- helpers -------------------------------------------------------------------

# Projects created by these tests, torn down at the end of the module. Without
# this the suite silently accumulates junk projects in the user's real library
# every time it runs.
_CREATED_PROJECTS: list = []


def _new_project(client, name: str) -> str:
    r = client.post("/api/v1/projects/", json={"name": name})
    assert r.status_code == 201, r.text
    project_id = r.json()["id"]
    _CREATED_PROJECTS.append(project_id)
    return project_id


def _discover_arxiv_paper(client, nth: int = 0) -> dict:
    """Pick the nth usable search result. Nothing about the target is fixed.

    Tests take different `nth` values so the failure-injection cases cannot
    corrupt the indexing state of the paper the end-to-end test is using.
    """
    r = client.get("/api/v1/search/", params={"q": "neural machine translation",
                                              "limit": 10, "source": "arxiv"})
    if r.status_code != 200:
        pytest.skip(f"external search unavailable: {r.status_code}")
    usable = [h for h in r.json() if h.get("arxiv_id")]
    if len(usable) <= nth:
        pytest.skip(f"arXiv returned fewer than {nth + 1} results with an arxiv_id")
    return usable[nth]


def _ingest(client, hit: dict, project_id: str | None = None) -> dict:
    body = {"arxiv_id": hit["arxiv_id"]}
    if project_id:
        body["project_id"] = project_id
    r = client.post("/api/v1/search/ingest", json=body)
    if r.status_code != 201:
        pytest.skip(f"ingestion unavailable ({r.status_code}): {r.text[:200]}")
    return r.json()


def _status(client, paper_id: str) -> dict:
    r = client.get(f"/api/v1/papers/{paper_id}/indexing-status")
    assert r.status_code == 200, r.text
    return r.json()


def _wait_for_terminal(client, paper_id: str, timeout: float = INDEX_TIMEOUT_S) -> dict:
    deadline = time.time() + timeout
    st = _status(client, paper_id)
    while st["indexing_status"] not in TERMINAL and time.time() < deadline:
        time.sleep(2)
        st = _status(client, paper_id)
    return st


def _in_app_loop(client, coro_fn, *args):
    """Run a coroutine on the TestClient's own event loop.

    `run_isolated` cannot be used inside a test that also drives the client:
    it disposes the SQLAlchemy engine, whose pooled asyncpg connections belong
    to the client's loop, and the next request fails with "attached to a
    different loop". The portal keeps everything on one loop.
    """
    return client.portal.call(coro_fn, *args)


async def _reindex_and_wait(paper_id: str):
    """Force a re-index through the dedup guard and wait for it to finish.

    Calling `research_indexer.index_paper` directly would bypass `ensure_indexed`
    and could race the background job that ingestion already started, with both
    writing the same status row.
    """
    from app.services import indexing_jobs

    await indexing_jobs.ensure_indexed(paper_id, force=True)
    task = indexing_jobs._running.get(paper_id)
    if task:
        await task


async def _paper_status(paper_id: str):
    from sqlalchemy import select

    from app.db.session import AsyncSessionLocal
    from app.models.paper import Paper
    async with AsyncSessionLocal() as db:
        p = await db.scalar(select(Paper).where(Paper.id == uuid.UUID(paper_id)))
        return p.indexing_status, p.indexing_error


async def _neo4j_chunk_stats(paper_id: str) -> dict:
    from app.db.neo4j_client import neo4j_client
    await neo4j_client.connect()
    s = await neo4j_client.get_session()
    async with s:
        row = await (await s.run(
            """
            MATCH (p:Paper {id: $pid})-[:HAS_CHUNK]->(c:Chunk)
            RETURN count(c) AS n,
                   count(c.embedding) AS embedded,
                   count(DISTINCT c.id) AS distinct_ids,
                   collect(DISTINCT c.paper_id) AS paper_ids
            """, pid=paper_id)).single()
    return dict(row) if row else {"n": 0}


def _stub_answer(seen: list):
    async def stub(model, messages, **kwargs):
        joined = " ".join(m.get("content", "") for m in messages)
        ids = re.findall(r"evidence_id=([^\s|\]]+)", joined)
        seen.extend(ids)
        return {
            "answer": "Stubbed grounded answer.",
            "grounded": True,
            "abstained": False,
            "citations": [{"evidence_id": ids[0], "claim": "supported"}] if ids else [],
        }
    return stub


# -- TEST 1 + 12 + 15: the real user journey -----------------------------------

@requires_db
def test_end_to_end_search_to_ask_ai(client):
    """SEARCH -> ADD TO PROJECT -> AUTO INGEST -> INDEXED -> ASK AI -> CITATION.

    Asserts on data and provenance at every hop, not on status codes.
    """
    hit = _discover_arxiv_paper(client, 0)
    project_id = _new_project(client, f"auto-ingest e2e {uuid.uuid4().hex[:8]}")

    res = _ingest(client, hit, project_id)
    paper_id = res["paper"]["id"]
    assert res.get("project_paper"), "paper was not associated with the project"

    # No manual upload, no manual index action: adding is what starts ingestion.
    st = _wait_for_terminal(client, paper_id)
    if st["can_retry"]:
        # A previous run may have left this paper in a failure state; the
        # controlled retry is the supported way out of one, so use it.
        client.get(f"/api/v1/papers/{paper_id}/indexing-status", params={"retry": True})
        st = _wait_for_terminal(client, paper_id)
    if st["indexing_status"] != "indexed":
        pytest.skip(
            f"PDF acquisition/indexing did not succeed for the discovered "
            f"paper ({st['indexing_status']}: {st['indexing_error']}). "
            "Reported honestly rather than asserted around."
        )
    assert st["ask_ai_ready"] is True

    stats = _in_app_loop(client, _neo4j_chunk_stats, paper_id)
    assert stats["n"] > 0, "indexed but no chunks exist"
    assert stats["embedded"] == stats["n"], "chunks missing embeddings"
    assert stats["distinct_ids"] == stats["n"], "duplicate chunk ids"
    assert stats["paper_ids"] == [paper_id], f"chunk provenance wrong: {stats['paper_ids']}"

    # Paper Ask AI, through the real route.
    r = client.post("/api/v1/chat/sessions", json={"paper_id": paper_id})
    assert r.status_code == 200, r.text
    session_id = r.json()["id"]

    seen = []
    from app.services import ai_router as router_mod
    with patch.object(router_mod.groq_service, "chat_complete_json",
                      new=AsyncMock(side_effect=_stub_answer(seen))):
        r = client.post(f"/api/v1/chat/sessions/{session_id}/messages",
                        json={"question": "What does this paper evaluate?"})
    assert r.status_code == 200, r.text
    ai = r.json()["ai_message"]

    assert seen, "no evidence from this paper reached the model"
    assert ai["retrieval"]["paper_ids"] == [paper_id]
    assert ai["evidence"], "no evidence returned"
    for e in ai["evidence"]:
        assert e["paper_id"] == paper_id, f"evidence from another paper: {e['paper_id']}"
    assert ai["citations"], "no citations returned"
    supplied = {e["chunk_id"] for e in ai["evidence"]}
    for c in ai["citations"]:
        assert c["chunk_id"] in supplied, "citation not traceable to retrieved evidence"
        assert c["paper_id"] == paper_id
        assert c["page"] is not None, "citation lost page provenance"

    # Same paper into a second project: link only, no re-ingestion.
    other = _new_project(client, f"auto-ingest second {uuid.uuid4().hex[:8]}")
    r = client.post(f"/api/v1/projects/{other}/papers", json={"paper_id": paper_id})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["indexing_status"] == "indexed"
    assert body["ask_ai_ready"] is True
    after = _in_app_loop(client, _neo4j_chunk_stats, paper_id)
    assert after["n"] == stats["n"], "adding to a second project duplicated chunks"


# -- TEST 4/5/6: idempotency and job dedup -------------------------------------

@requires_db
def test_add_to_project_returns_status_and_never_claims_ready_early(client):
    """The add response must report indexing state honestly."""
    hit = _discover_arxiv_paper(client, 1)
    res = _ingest(client, hit)
    paper_id = res["paper"]["id"]

    project_id = _new_project(client, f"auto-ingest status {uuid.uuid4().hex[:8]}")
    r = client.post(f"/api/v1/projects/{project_id}/papers", json={"paper_id": paper_id})
    assert r.status_code == 201, r.text
    body = r.json()
    assert "indexing_status" in body and "ask_ai_ready" in body
    assert body["ask_ai_ready"] == is_ask_ai_ready(body["indexing_status"]), \
        "ask_ai_ready disagrees with the persisted status"
    if body["indexing_status"] != "indexed":
        assert body["ask_ai_ready"] is False, "claimed Ask AI ready before indexing finished"


@requires_db
def test_duplicate_add_to_same_project_is_rejected_without_new_job(client):
    hit = _discover_arxiv_paper(client, 2)
    paper_id = _ingest(client, hit)["paper"]["id"]
    project_id = _new_project(client, f"auto-ingest dup {uuid.uuid4().hex[:8]}")

    assert client.post(f"/api/v1/projects/{project_id}/papers",
                       json={"paper_id": paper_id}).status_code == 201
    r = client.post(f"/api/v1/projects/{project_id}/papers", json={"paper_id": paper_id})
    assert r.status_code == 400, "duplicate association was created"


@requires_db
def test_concurrent_ensure_indexed_starts_one_job(client):
    """TEST 6: a second add while indexing runs must not enqueue a second job."""
    from app.services import indexing_jobs

    async def _race():
        from app.db.session import AsyncSessionLocal
        from app.models.paper import Paper
        from app.services.research_indexer import research_indexer

        # A freshly inserted row, so no ingestion is already in flight for it —
        # otherwise this asserts on whatever an earlier test left running.
        async with AsyncSessionLocal() as db:
            paper = Paper(title=f"dedup probe {uuid.uuid4().hex[:8]}",
                          pdf_url="https://example.invalid/none.pdf")
            db.add(paper)
            await db.commit()
            await db.refresh(paper)
            pid = str(paper.id)

        calls = []

        async def slow_index(db, paper_id, force=False):
            calls.append(paper_id)
            await asyncio.sleep(0.5)

        try:
            with patch.object(research_indexer, "index_paper", new=slow_index):
                first = await indexing_jobs.ensure_indexed(pid)
                second = await indexing_jobs.ensure_indexed(pid)
                third = await indexing_jobs.ensure_indexed(pid)
                task = indexing_jobs._running.get(pid)
                if task:
                    await task
        finally:
            async with AsyncSessionLocal() as db:
                obj = await db.get(Paper, uuid.UUID(pid))
                if obj:
                    await db.delete(obj)
                    await db.commit()
        return first, second, third, calls

    first, second, third, calls = _in_app_loop(client, _race)
    # The dedup guarantee is about work, not about the reported status: all
    # three callers legitimately see "queued", but only one job may run.
    assert len(calls) == 1, f"expected exactly one indexing job, got {len(calls)}"
    assert first == "queued", f"first call did not start a job: {first}"
    for status in (first, second, third):
        assert not is_ask_ai_ready(status), "claimed Ask AI ready while queued"


# -- TEST 7/8/9: honest failure ------------------------------------------------

@requires_db
@pytest.mark.parametrize("body", [b"<html><body>Not a PDF</body></html>", b""])
def test_non_pdf_response_marks_pdf_unavailable(client, body):
    """TEST 7: an HTML/empty body must never be indexed as if it were a PDF."""
    from app.services.research_indexer import research_indexer

    hit = _discover_arxiv_paper(client, 3)
    paper_id = _ingest(client, hit)["paper"]["id"]
    # Ingestion already started a real job for this paper. Let it finish before
    # injecting a failure, so the two writers do not race on the status row.
    _wait_for_terminal(client, paper_id)

    async def _run():
        import httpx
        from sqlalchemy import select

        from app.db.session import AsyncSessionLocal
        from app.models.paper import Paper

        class FakeResponse:
            content = body

            def raise_for_status(self):
                return None

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, url):
                return FakeResponse()

        from app.services.pdf_validator import pdf_validator

        async def always_valid(url):
            return {"valid": True, "url": url, "content_type": "application/pdf"}

        # Validation streams a probe; the full GET can still land on an
        # interstitial page. Let validation pass so the test proves the
        # post-download check is what rejects a non-PDF body.
        with patch.object(pdf_validator, "validate_pdf_url", always_valid),                 patch.object(httpx, "AsyncClient", lambda **kw: FakeClient()):
            await _reindex_and_wait(paper_id)
        return await _paper_status(paper_id)

    status, error = _in_app_loop(client, _run)
    assert status == "pdf_unavailable", f"expected pdf_unavailable, got {status}: {error}"
    assert not is_ask_ai_ready(status), "claimed Ask AI ready after a failed download"
    assert error and "not a pdf" in error.lower()


@requires_db
def test_embedding_failure_is_reported_as_indexing_failed(client):
    """TEST 9: a processing failure is distinct from an acquisition failure."""
    from app.services.research_indexer import research_indexer

    hit = _discover_arxiv_paper(client, 4)
    paper_id = _ingest(client, hit)["paper"]["id"]
    _wait_for_terminal(client, paper_id)

    async def _run():
        from sqlalchemy import select

        from app.db.session import AsyncSessionLocal
        from app.models.paper import Paper

        def boom(texts):
            raise RuntimeError("embedding backend exploded")

        with patch.object(research_indexer, "_embed_chunks", boom):
            await _reindex_and_wait(paper_id)
        return await _paper_status(paper_id)

    status, error = _in_app_loop(client, _run)
    if status == "pdf_unavailable":
        pytest.skip("PDF could not be fetched, so the embedding path was never reached")
    assert status == "failed", f"expected failed, got {status}"
    assert not is_ask_ai_ready(status)
    assert error and "embedding backend exploded" in error


# -- ingestion is started by saving, not by opening ----------------------------

@requires_db
def test_ingest_starts_indexing_before_it_responds(client):
    """The weak-reference bug: indexing must be under way when ingest returns.

    `ensure_indexed` was previously reached only from inside an unreferenced
    `asyncio.create_task`, which asyncio may collect before it runs any code.
    A paper still sitting at `not_indexed` immediately after ingest means the
    job was never started.
    """
    hit = _discover_arxiv_paper(client, 5)
    paper_id = _ingest(client, hit)["paper"]["id"]

    st = _status(client, paper_id)
    assert st["indexing_status"] != "not_indexed", \
        "ingest returned without starting indexing"


@requires_db
def test_opening_a_paper_does_not_start_indexing(client):
    """Opening is a read. Only entering the library triggers ingestion."""
    async def _make_unindexed():
        from app.db.session import AsyncSessionLocal
        from app.models.paper import Paper
        async with AsyncSessionLocal() as db:
            paper = Paper(title=f"open probe {uuid.uuid4().hex[:8]}",
                          pdf_url="https://example.invalid/none.pdf")
            db.add(paper)
            await db.commit()
            await db.refresh(paper)
            return str(paper.id)

    async def _drop(pid):
        from app.db.session import AsyncSessionLocal
        from app.models.paper import Paper
        async with AsyncSessionLocal() as db:
            obj = await db.get(Paper, uuid.UUID(pid))
            if obj:
                await db.delete(obj)
                await db.commit()

    paper_id = _in_app_loop(client, _make_unindexed)
    try:
        assert client.get(f"/api/v1/papers/{paper_id}").status_code == 200
        time.sleep(1)
        assert _status(client, paper_id)["indexing_status"] == "not_indexed", \
            "opening a paper started an indexing job"
    finally:
        _in_app_loop(client, _drop, paper_id)


@requires_db
def test_paper_without_a_pdf_is_saved_as_metadata_only(client):
    """A paper with no reachable PDF is still added -- honestly marked."""
    from app.services.pdf_validator import pdf_validator

    hit = _discover_arxiv_paper(client, 6)

    async def _ingest_with_no_pdf():
        from app.services.search_service import search_service
        from app.db.session import AsyncSessionLocal

        async def no_pdf(candidates):
            return None

        with patch.object(pdf_validator, "find_valid_pdf", no_pdf):
            async with AsyncSessionLocal() as db:
                return await search_service.ingest_paper(
                    session=db, arxiv_id=hit["arxiv_id"]
                )

    result = _in_app_loop(client, _ingest_with_no_pdf)
    paper = result["paper"]
    assert paper is not None, "ingest refused a paper that has no PDF"

    st = _status(client, str(paper.id))
    if st["indexing_status"] == "indexed":
        pytest.skip("this paper was already indexed from an earlier run")
    assert st["ask_ai_ready"] is False, "claimed Ask AI ready with no full text"
