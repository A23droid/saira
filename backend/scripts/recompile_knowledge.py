"""
Reconcile paper indexing status after the LLM-Wiki / OKF migration.

Papers indexed by the GraphRAG pipeline have their chunks and embeddings in
Neo4j, which no longer exists at runtime. Their `indexing_status` still says
`indexed`, so `ask_ai_ready` is true and the UI offers Ask AI — but knowledge
retrieval finds nothing, and the model correctly abstains on every question.
That is the worst failure shape available: confidently available, silently
empty.

This script finds papers claiming `indexed` with no rows in
`knowledge_entries` and, by default, resets them to `not_indexed`. The normal
on-demand path (`ensure_indexed`, triggered by opening or saving a paper) then
recompiles them properly.

Run from the `backend/` directory — settings read `.env` relative to the
working directory, so running from the repository root picks up defaults
instead of your real database URL.

    cd backend
    venv/Scripts/python.exe scripts/recompile_knowledge.py --dry-run
    venv/Scripts/python.exe scripts/recompile_knowledge.py
    venv/Scripts/python.exe scripts/recompile_knowledge.py --recompile 5

ponytail: reset-and-let-it-recompile is the default because it is free and
self-healing. `--recompile` exists for warming the papers people actually use
before they notice.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    parser.add_argument(
        "--recompile", type=int, default=0, metavar="N",
        help="after resetting, actively recompile the N papers saved in the most projects",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from sqlalchemy import func, select

    from app.db.session import AsyncSessionLocal, engine
    from app.models.knowledge import KnowledgeEntry
    from app.models.paper import Paper
    from app.models.project_paper import ProjectPaper

    async with AsyncSessionLocal() as db:
        stale_stmt = (
            select(Paper.id, Paper.title)
            .where(
                Paper.indexing_status == "indexed",
                ~select(KnowledgeEntry.id)
                .where(KnowledgeEntry.paper_id == Paper.id)
                .exists(),
            )
            .order_by(Paper.created_at)
        )
        stale = (await db.execute(stale_stmt)).all()

        print(f"{len(stale)} paper(s) marked 'indexed' with no compiled knowledge")
        if args.dry_run:
            for pid, title in stale[:20]:
                print(f"  would reset {pid}  {(title or '')[:70]}")
            if len(stale) > 20:
                print(f"  ... and {len(stale) - 20} more")
            await engine.dispose()
            return 0

        for pid, _ in stale:
            paper = await db.get(Paper, pid)
            if paper:
                paper.indexing_status = "not_indexed"
                paper.indexing_error = None
        await db.commit()
        print(f"reset {len(stale)} paper(s) to 'not_indexed'")

        if not args.recompile:
            print("They will recompile on next open or save. Use --recompile N to warm now.")
            await engine.dispose()
            return 0

        # Warm the papers that are actually in someone's project first — those
        # are the ones a user will hit.
        popular_stmt = (
            select(ProjectPaper.paper_id, func.count(ProjectPaper.id).label("n"))
            .group_by(ProjectPaper.paper_id)
            .order_by(func.count(ProjectPaper.id).desc())
            .limit(args.recompile)
        )
        targets = [r[0] for r in (await db.execute(popular_stmt)).all()]

    if not targets:
        print("No saved papers to recompile.")
        await engine.dispose()
        return 0

    from app.services.indexing_jobs import ensure_indexed

    print(f"\nrecompiling {len(targets)} paper(s)...")
    tasks = []
    for pid in targets:
        status = await ensure_indexed(pid, force=True)
        print(f"  queued {pid} (status={status})")

    # `ensure_indexed` returns as soon as the job is queued and keeps its own
    # strong reference, so wait for the registry to drain before exiting —
    # otherwise the process dies mid-compilation.
    from app.services.indexing_jobs import _running

    while any(not t.done() for t in list(_running.values())):
        await asyncio.sleep(2)
        print(f"  ... {sum(1 for t in _running.values() if not t.done())} still running")

    async with AsyncSessionLocal() as db:
        for pid in targets:
            paper = await db.get(Paper, pid)
            if paper:
                print(f"  {pid}: {paper.indexing_status} {paper.indexing_error or ''}")

    await engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
