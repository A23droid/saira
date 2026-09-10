"""
Ephemeral vs persistent Paper Chat.

A paper chat is persistent only while the paper is saved in one of the caller's
projects. These tests drive the real HTTP routes and assert on stored state --
that nothing was written for an unsaved paper, and that what was written for a
saved one comes back in order.

Generation is stubbed; retrieval, scope resolution, citation validation and
persistence all run for real, so the suite is deterministic and spends no
provider quota.

Two papers are used deliberately: one that must stay unsaved for the whole
module, and one that gets promoted. Sharing a single paper would let the
promotion tests destroy the premise of the ephemeral ones.

Requires live Postgres + Neo4j + network; skips (never silently passes) without.
"""

from __future__ import annotations

import asyncio
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
from app.core.config import settings  # noqa: E402
from app.main import app  # noqa: E402

TERMINAL = {"indexed", "failed", "pdf_unavailable"}
INDEX_TIMEOUT_S = 300

_CREATED_PROJECTS: list = []


async def _probe():
    from sqlalchemy import select

    from app.db.session import AsyncSessionLocal
    from app.models.user import User

    async with AsyncSessionLocal() as db:
        user = await db.scalar(select(User).limit(1))
        if not user:
            return None
        other = await db.scalar(select(User).where(User.id != user.id).limit(1))
        return {
            "user_id": str(user.id),
            "other_user_id": str(other.id) if other else None,
        }


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
            from app.db.session import engine
            await engine.dispose()
        try:
            asyncio.run(_dispose())
        except Exception:
            pass


# -- helpers -------------------------------------------------------------------


def _new_project(client, name: str) -> str:
    r = client.post("/api/v1/projects/", json={"name": name})
    assert r.status_code == 201, r.text
    project_id = r.json()["id"]
    _CREATED_PROJECTS.append(project_id)
    return project_id


def _paper(client, nth: int) -> str:
    """Ingest the nth arXiv result and wait for indexing to settle.

    The paper does not have to become answerable: mode, persistence and
    promotion are decided from the project association alone, so those tests
    only need the paper to exist. Tests that actually put a question to the
    model call `_require_answerable` for themselves.
    """
    r = client.get("/api/v1/search/", params={"q": "graph neural network",
                                              "limit": 10, "source": "arxiv"})
    if r.status_code != 200:
        pytest.skip(f"external search unavailable: {r.status_code}")
    usable = [h for h in r.json() if h.get("arxiv_id")]
    if len(usable) <= nth:
        pytest.skip(f"arXiv returned fewer than {nth + 1} results with an arxiv_id")

    r = client.post("/api/v1/search/ingest", json={"arxiv_id": usable[nth]["arxiv_id"]})
    if r.status_code != 201:
        pytest.skip(f"ingestion unavailable ({r.status_code}): {r.text[:200]}")
    paper_id = r.json()["paper"]["id"]

    deadline = time.time() + INDEX_TIMEOUT_S
    st = client.get(f"/api/v1/papers/{paper_id}/indexing-status").json()
    while st["indexing_status"] not in TERMINAL and time.time() < deadline:
        time.sleep(2)
        st = client.get(f"/api/v1/papers/{paper_id}/indexing-status").json()
    return paper_id


def _require_answerable(client, paper_id: str) -> None:
    st = client.get(f"/api/v1/papers/{paper_id}/indexing-status").json()
    if not st["ask_ai_ready"]:
        pytest.skip(f"paper has no chunks to retrieve: {st['indexing_status']}")


def _clear_paper_sessions(client, paper_id: str) -> None:
    """Drop persistent sessions for this paper, before and after the module.

    Projects are torn down by the client fixture, which takes the project_papers
    rows with them -- but a promoted chat session outlives its project and would
    make the next run start from a state the first run never saw. There is no
    delete endpoint for chat sessions (the product has no need of one), so this
    goes through the DB on the client's own event loop.
    """
    async def _delete(pid: str):
        from sqlalchemy import delete

        from app.db.session import AsyncSessionLocal
        from app.models.chat import ChatSession
        async with AsyncSessionLocal() as db:
            await db.execute(delete(ChatSession).where(
                ChatSession.user_id == uuid.UUID(CTX["user_id"]),
                ChatSession.paper_id == uuid.UUID(pid),
            ))
            await db.commit()

    client.portal.call(_delete, paper_id)


@pytest.fixture(scope="module")
def ephemeral_paper(client):
    """Never saved to a project by any test in this module."""
    paper_id = _paper(client, 0)
    _clear_paper_sessions(client, paper_id)
    yield paper_id
    _clear_paper_sessions(client, paper_id)


@pytest.fixture(scope="module")
def promotable_paper(client):
    """Saved partway through, to exercise ephemeral -> persistent."""
    paper_id = _paper(client, 1)
    _clear_paper_sessions(client, paper_id)
    yield paper_id
    _clear_paper_sessions(client, paper_id)


def _stub(seen_payloads: list):
    """Records every message array the model was handed, and cites real evidence."""
    async def stub(model, messages, **kwargs):
        import re
        seen_payloads.append(messages)
        joined = " ".join(m.get("content", "") for m in messages)
        ids = re.findall(r"evidence_id=([^\s|\]]+)", joined)
        return {
            "answer": "Stubbed grounded answer.",
            "grounded": True,
            "abstained": False,
            "citations": [{"evidence_id": ids[0], "claim": "supported"}] if ids else [],
        }
    return stub


def _ask_ephemeral(client, paper_id: str, question: str, history: list, seen: list):
    from app.services import ai_router as router_mod

    with patch.object(router_mod.groq_service, "chat_complete_json",
                      new=AsyncMock(side_effect=_stub(seen))):
        return client.post(f"/api/v1/chat/papers/{paper_id}/ephemeral",
                           json={"question": question, "history": history})


def _ask_persistent(client, session_id: str, question: str, seen: list):
    from app.services import ai_router as router_mod

    with patch.object(router_mod.groq_service, "chat_complete_json",
                      new=AsyncMock(side_effect=_stub(seen))):
        return client.post(f"/api/v1/chat/sessions/{session_id}/messages",
                           json={"question": question})


def _context(client, paper_id: str) -> dict:
    r = client.get(f"/api/v1/chat/papers/{paper_id}/context")
    assert r.status_code == 200, r.text
    return r.json()


def _paper_sessions(client, paper_id: str) -> list:
    r = client.get("/api/v1/chat/sessions", params={"paper_id": paper_id})
    assert r.status_code == 200, r.text
    return r.json()


# -- ephemeral -----------------------------------------------------------------


@requires_db
def test_unsaved_paper_opens_in_ephemeral_mode(client, ephemeral_paper):
    """TEST 1 -- an unsaved paper gets a temporary chat and no session row."""
    ctx = _context(client, ephemeral_paper)
    assert ctx["mode"] == "ephemeral"
    assert ctx["session_id"] is None
    assert ctx["messages"] == []
    assert _paper_sessions(client, ephemeral_paper) == [], \
        "opening an unsaved paper created a persistent session"


@requires_db
def test_ephemeral_conversation_carries_context(client, ephemeral_paper):
    """TEST 2 -- the second question is answered with the first turn in view."""
    # The evaluation harness turns eval mode on globally, and eval mode drops
    # history on purpose so a previous answer cannot supply a fact the current
    # retrieval did not. This test is about product behaviour, so it asserts
    # against the shipping configuration.
    with patch.object(type(settings), "eval_mode", property(lambda self: False)):
        seen: list = []
        r = _ask_ephemeral(client, ephemeral_paper, "What problem does this paper solve?",
                           [], seen)
        assert r.status_code == 200, r.text
        first_answer = r.json()["ai_message"]["content"]

        history = [
            {"role": "user", "content": "What problem does this paper solve?"},
            {"role": "assistant", "content": first_answer},
        ]
        r = _ask_ephemeral(client, ephemeral_paper, "And what dataset do they use?",
                           history, seen)
        assert r.status_code == 200, r.text

        # The prior turn must actually be in the payload -- not merely accepted.
        second_payload = " ".join(m.get("content", "") for m in seen[-1])
        assert "What problem does this paper solve?" in second_payload, \
            "previous turn did not reach the model"


@requires_db
def test_ephemeral_chat_persists_nothing(client, ephemeral_paper):
    """TEST 3 -- after asking, there is still no stored history anywhere."""
    seen: list = []
    assert _ask_ephemeral(client, ephemeral_paper, "Summarise the method.",
                          [], seen).status_code == 200

    assert _paper_sessions(client, ephemeral_paper) == []
    assert _context(client, ephemeral_paper)["messages"] == []


@requires_db
def test_reopening_an_unsaved_paper_restores_nothing(client, ephemeral_paper):
    """TEST 4 -- a fresh open is a fresh conversation."""
    seen: list = []
    _ask_ephemeral(client, ephemeral_paper, "One more question.", [], seen)

    ctx = _context(client, ephemeral_paper)
    assert ctx["mode"] == "ephemeral"
    assert ctx["messages"] == [], "an ephemeral conversation came back after reopen"


@requires_db
def test_persistent_session_refused_for_unsaved_paper(client, ephemeral_paper):
    """The ephemeral rule is enforced server-side, not just in the UI."""
    r = client.post("/api/v1/chat/sessions", json={"paper_id": ephemeral_paper})
    assert r.status_code == 409, r.text
    assert _paper_sessions(client, ephemeral_paper) == []


@requires_db
def test_promote_refused_before_the_paper_is_saved(client, ephemeral_paper):
    """Promotion cannot manufacture history for a paper that was never kept."""
    r = client.post(f"/api/v1/chat/papers/{ephemeral_paper}/promote",
                    json={"messages": [{"role": "user", "content": "smuggled"}]})
    assert r.status_code == 409, r.text
    assert _paper_sessions(client, ephemeral_paper) == []


@requires_db
def test_ephemeral_retrieval_stays_inside_the_paper(client, ephemeral_paper,
                                                    promotable_paper):
    """TEST 9 / TEST 14 -- evidence comes only from the paper being asked about,
    and a temporary paper's chunks do not leak into another paper's chat."""
    _require_answerable(client, ephemeral_paper)

    seen: list = []
    r = _ask_ephemeral(client, ephemeral_paper, "What is the contribution?", [], seen)
    assert r.status_code == 200, r.text
    ai = r.json()["ai_message"]

    assert ai["evidence"], "no evidence was retrieved"
    for e in ai["evidence"]:
        assert e["paper_id"] == ephemeral_paper, f"evidence from another paper: {e}"
    assert promotable_paper not in {e["paper_id"] for e in ai["evidence"]}


# -- promotion and persistence -------------------------------------------------


@requires_db
def test_saving_mid_chat_promotes_the_conversation(client, promotable_paper):
    """TEST 5 -- add to project, then the live conversation becomes the stored one."""
    seen: list = []
    r = _ask_ephemeral(client, promotable_paper, "What is the main contribution?",
                       [], seen)
    assert r.status_code == 200, r.text
    answer = r.json()["ai_message"]["content"]
    assert _paper_sessions(client, promotable_paper) == []

    project_id = _new_project(client, f"chat-mode-{uuid.uuid4().hex[:8]}")
    r = client.post(f"/api/v1/projects/{project_id}/papers",
                    json={"paper_id": promotable_paper})
    assert r.status_code == 201, r.text

    conversation = [
        {"role": "user", "content": "What is the main contribution?"},
        {"role": "assistant", "content": answer},
    ]
    r = client.post(f"/api/v1/chat/papers/{promotable_paper}/promote",
                    json={"messages": conversation})
    assert r.status_code == 200, r.text
    assert r.json()["mode"] == "persistent"
    assert r.json()["migrated"] == 2

    ctx = _context(client, promotable_paper)
    assert ctx["mode"] == "persistent"
    assert [m["content"] for m in ctx["messages"]] == [c["content"] for c in conversation], \
        "migrated conversation came back altered or out of order"


@requires_db
def test_reopening_a_saved_paper_restores_history(client, promotable_paper):
    """TEST 6 / TEST 7 -- a reopen (which is all a refresh is) restores the chat."""
    first = _context(client, promotable_paper)
    second = _context(client, promotable_paper)

    assert second["mode"] == "persistent"
    assert second["session_id"] == first["session_id"]
    assert len(second["messages"]) >= 2
    assert [m["content"] for m in second["messages"]] == \
           [m["content"] for m in first["messages"]]


@requires_db
def test_persistent_follow_up_is_stored_in_order(client, promotable_paper):
    """TEST 8 -- a new turn is appended, and the transcript stays coherent."""
    ctx = _context(client, promotable_paper)
    before = len(ctx["messages"])

    seen: list = []
    r = _ask_persistent(client, ctx["session_id"],
                        "Can you explain that contribution further?", seen)
    assert r.status_code == 200, r.text

    after = _context(client, promotable_paper)["messages"]
    assert len(after) == before + 2
    assert after[-2]["role"] == "user"
    assert after[-2]["content"] == "Can you explain that contribution further?"
    assert after[-1]["role"] == "assistant", \
        "question and answer came back in the wrong order"


@requires_db
def test_repeated_opens_do_not_duplicate_the_session(client, promotable_paper):
    """TEST 11 -- opening a saved paper repeatedly keeps one conversation."""
    ids = {_context(client, promotable_paper)["session_id"] for _ in range(4)}
    assert len(ids) == 1, f"reopening created extra sessions: {ids}"
    assert len(_paper_sessions(client, promotable_paper)) == 1


@requires_db
def test_saving_to_a_second_project_reuses_the_same_chat(client, promotable_paper):
    """TEST 12 -- a duplicate save creates no second session and no second paper.

    Chat identity is (user, paper); this pins that decision down so a later
    change to project-scoped chat has to break a test rather than slip through.
    """
    before = _context(client, promotable_paper)

    other = _new_project(client, f"chat-mode-2-{uuid.uuid4().hex[:8]}")
    r = client.post(f"/api/v1/projects/{other}/papers", json={"paper_id": promotable_paper})
    assert r.status_code == 201, r.text

    after = _context(client, promotable_paper)
    assert after["session_id"] == before["session_id"]
    assert len(_paper_sessions(client, promotable_paper)) == 1
    assert [m["content"] for m in after["messages"]] == \
           [m["content"] for m in before["messages"]]


@requires_db
def test_promotion_is_idempotent(client, promotable_paper):
    """A retried promotion must not duplicate the conversation."""
    before = _context(client, promotable_paper)["messages"]

    r = client.post(f"/api/v1/chat/papers/{promotable_paper}/promote",
                    json={"messages": [{"role": "user", "content": "should not appear"}]})
    assert r.status_code == 200, r.text
    assert r.json()["migrated"] == 0, "promotion wrote into a non-empty session"

    after = _context(client, promotable_paper)["messages"]
    assert [m["content"] for m in after] == [m["content"] for m in before]


@requires_db
def test_saved_paper_rejects_the_ephemeral_endpoint(client, promotable_paper):
    """Once saved, answers must go through the session so they are stored."""
    r = client.post(f"/api/v1/chat/papers/{promotable_paper}/ephemeral",
                    json={"question": "anything", "history": []})
    assert r.status_code == 409, r.text


@requires_db
def test_add_to_project_still_reports_ingestion(client, promotable_paper):
    """TEST 13 -- the automatic-ingestion contract is unchanged by this feature."""
    project_id = _new_project(client, f"chat-mode-3-{uuid.uuid4().hex[:8]}")
    r = client.post(f"/api/v1/projects/{project_id}/papers",
                    json={"paper_id": promotable_paper})
    assert r.status_code == 201, r.text
    body = r.json()
    assert "indexing_status" in body and "ask_ai_ready" in body
    assert body["ask_ai_ready"] is (body["indexing_status"] == "indexed")


# -- authorization -------------------------------------------------------------


@requires_db
def test_another_users_paper_chat_cannot_be_loaded(client, promotable_paper):
    """TEST 10 -- persistent history is scoped to its owner, by session and by paper."""
    if not CTX.get("other_user_id"):
        pytest.skip("only one user in the database -- cannot test cross-user access")

    session_id = _context(client, promotable_paper)["session_id"]

    async def other_user():
        from sqlalchemy import select

        from app.db.session import AsyncSessionLocal
        from app.models.user import User
        async with AsyncSessionLocal() as db:
            return await db.scalar(
                select(User).where(User.id == uuid.UUID(CTX["other_user_id"]))
            )

    previous = app.dependency_overrides[get_current_user]
    app.dependency_overrides[get_current_user] = other_user
    try:
        r = client.get(f"/api/v1/chat/sessions/{session_id}")
        assert r.status_code == 404, \
            f"another user loaded a paper chat they do not own: {r.status_code}"

        # The paper is in someone else's project, so for this user it is unsaved:
        # they get their own empty ephemeral chat, never the owner's transcript.
        ctx = _context(client, promotable_paper)
        assert ctx["mode"] == "ephemeral"
        assert ctx["session_id"] != session_id
        assert ctx["messages"] == []
    finally:
        app.dependency_overrides[get_current_user] = previous
