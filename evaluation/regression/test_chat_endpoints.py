"""
Endpoint-level regression tests for Paper Chat and Project Chat.

These exercise the real FastAPI routes — scope resolution, retrieval,
citation validation, and persistence — with the model call stubbed. Stubbing
generation keeps them deterministic and free of provider quota while still
covering everything around it, which is where the scoping and citation bugs
actually lived.

Requires live Postgres; skips (never silently passes) without it.
"""

from __future__ import annotations

import asyncio
import sys
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


async def _probe():
    """Find a user, a paper with compiled knowledge, and a project they own."""
    from sqlalchemy import select

    from app.db.session import AsyncSessionLocal
    from app.models.project import Project
    from app.models.user import User

    async with AsyncSessionLocal() as db:
        user = await db.scalar(select(User).limit(1))
        if user is None:
            return None
        project = await db.scalar(select(Project).where(Project.user_id == user.id).limit(1))
        # Look this up now, before the TestClient exists. Running a separate
        # event loop inside a test would dispose the engine the client's
        # connections are bound to.
        foreign = await db.scalar(select(Project).where(Project.user_id != user.id).limit(1))
        # Papers carrying compiled knowledge, most-indexed first. Replaces the
        # Neo4j chunk-count probe.
        from sqlalchemy import text as _sql

        rows = (await db.execute(_sql("""
            SELECT paper_id::text AS id, count(*) AS n
            FROM knowledge_entries
            GROUP BY paper_id
            ORDER BY n DESC
            LIMIT 25
        """))).mappings().all()

        # A persistent paper chat session now requires the paper to be saved in
        # one of this user's projects, so the target has to be a saved paper --
        # the most-chunked paper overall may be one nobody kept.
        from app.models.project_paper import ProjectPaper

        paper_id = None
        for row in rows:
            saved = await db.scalar(
                select(ProjectPaper.id)
                .join(Project, Project.id == ProjectPaper.project_id)
                .where(ProjectPaper.paper_id == uuid.UUID(row["id"]),
                       Project.user_id == user.id)
                .limit(1)
            )
            if saved:
                paper_id = row["id"]
                break

        return {
            "user_id": str(user.id),
            "project_id": str(project.id) if project else None,
            "foreign_project_id": str(foreign.id) if foreign else None,
            "paper_id": paper_id,
        }


try:
    CTX = run_isolated(_probe())
except Exception:
    CTX = None

requires_data = pytest.mark.skipif(
    not CTX or not CTX.get("paper_id"),
    reason="Postgres unavailable or no compiled paper — skipped, not passed.",
)


@pytest.fixture(scope="module")
def client():
    async def fake_user():
        from sqlalchemy import select

        from app.db.session import AsyncSessionLocal
        from app.models.user import User
        async with AsyncSessionLocal() as db:
            return await db.scalar(select(User).where(User.id == uuid.UUID(CTX["user_id"])))

    # Save and restore rather than pop: other test modules install their own
    # override at import time, and popping unconditionally left them
    # unauthenticated (401) for the rest of the session.
    previous = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = fake_user
    try:
        with TestClient(app) as c:
            yield c
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = previous
        # The TestClient portal owned an event loop that the async engine
        # pooled connections against. Release them so the next module's fresh
        # loop does not inherit sockets bound to a dead one.
        async def _dispose():
            from app.db.session import engine
            await engine.dispose()
        # Best effort: the portal's loop is already closing, so a failure to
        # drain it must not turn teardown into a test error.
        try:
            asyncio.run(_dispose())
        except Exception:
            pass


def _stub_answer(evidence_ids_from):
    """Build a stub that cites whatever evidence it is actually given."""
    async def stub(model, messages, **kwargs):
        import re
        joined = " ".join(m.get("content", "") for m in messages)
        ids = re.findall(r"evidence_id=([^\s|\]]+)", joined)
        evidence_ids_from.extend(ids)
        return {
            "answer": "Stubbed grounded answer.",
            "grounded": True,
            "abstained": False,
            # Cite the first real id plus one that was never supplied.
            "citations": (
                ([{"evidence_id": ids[0], "claim": "supported claim"}] if ids else [])
                + [{"evidence_id": "NOT-SUPPLIED-999", "claim": "fabricated"}]
            ),
        }
    return stub


@requires_data
def test_paper_chat_returns_scoped_citations(client):
    """Paper Chat: answer carries citations traceable to in-scope evidence,
    and a fabricated citation never reaches the response."""
    from app.services import ai_router as router_mod

    r = client.post("/api/v1/chat/sessions",
                    json={"paper_id": CTX["paper_id"], "title": "regression"})
    assert r.status_code == 200, r.text
    session_id = r.json()["id"]

    seen: list[str] = []
    with patch.object(router_mod.groq_service, "chat_complete_json",
                      new=AsyncMock(side_effect=_stub_answer(seen))):
        r = client.post(f"/api/v1/chat/sessions/{session_id}/messages",
                        json={"question": "What method does this paper use?"})
    assert r.status_code == 200, r.text
    ai = r.json()["ai_message"]

    assert seen, "no evidence reached the model"
    assert ai["citations"], "no citations returned"
    supplied = {e["chunk_id"] for e in ai["evidence"]}
    for c in ai["citations"]:
        assert c["chunk_id"] in supplied, "citation not traceable to supplied evidence"
        assert c["paper_id"] == CTX["paper_id"], "citation outside the paper scope"
        assert c["page"] is not None
    assert all(c["chunk_id"] != "NOT-SUPPLIED-999" for c in ai["citations"]), \
        "fabricated citation survived validation"

    # Retrieval must be scoped to the selected paper only.
    assert ai["retrieval"]["scope_type"] == "paper"
    assert ai["retrieval"]["paper_ids"] == [CTX["paper_id"]]
    assert ai["cited_paper_ids"] == [CTX["paper_id"]]


@requires_data
def test_chat_session_rejects_a_project_the_user_does_not_own(client):
    """The cross-tenant leak: a session may not be pointed at a foreign project."""
    foreign_id = CTX.get("foreign_project_id")
    if not foreign_id:
        pytest.skip("no project owned by a different user in this database")

    r = client.post("/api/v1/chat/sessions", json={"project_id": foreign_id})
    assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"


@requires_data
def test_chat_session_requires_a_context(client):
    r = client.post("/api/v1/chat/sessions", json={"title": "no context"})
    assert r.status_code == 400


@requires_data
def test_paper_chat_evidence_never_leaves_the_paper(client):
    """Invariant 1 at the HTTP boundary: no evidence from another paper."""
    from app.services import ai_router as router_mod

    r = client.post("/api/v1/chat/sessions", json={"paper_id": CTX["paper_id"]})
    session_id = r.json()["id"]

    seen: list[str] = []
    with patch.object(router_mod.groq_service, "chat_complete_json",
                      new=AsyncMock(side_effect=_stub_answer(seen))):
        r = client.post(f"/api/v1/chat/sessions/{session_id}/messages",
                        json={"question": "Describe the evaluation setup."})
    ai = r.json()["ai_message"]
    for e in ai["evidence"]:
        assert e["paper_id"] == CTX["paper_id"], (
            f"SCOPE LEAK: evidence from {e['paper_id']}")
