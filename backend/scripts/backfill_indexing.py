"""
One-off backfill for papers that were never indexed.

Opening a paper used to kick off indexing as a side effect, which made it
ambiguous what had actually triggered a job. That trigger is gone, so papers
added before automatic ingestion existed need indexing once, here.

Usage (from the repository root):
    backend/venv/Scripts/python.exe backend/scripts/backfill_indexing.py
    backend/scripts/backfill_indexing.py --status failed --retry
    backend/scripts/backfill_indexing.py --limit 5 --dry-run

Runs the canonical pipeline (`research_indexer.index_paper`) directly, a few
papers at a time, and reports what each one ended up as. It never reports
success for a paper that did not reach `indexed`.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections import Counter
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", default="not_indexed",
                        help="indexing_status to backfill (default: not_indexed)")
    parser.add_argument("--limit", type=int, default=0, help="0 = no limit")
    parser.add_argument("--concurrency", type=int, default=2,
                        help="papers indexed in parallel (default: 2)")
    parser.add_argument("--retry", action="store_true",
                        help="force re-index even if the paper is already indexed")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    from sqlalchemy import select

    from app.db.session import AsyncSessionLocal, engine
    from app.models.paper import Paper
    from app.services.research_indexer import research_indexer

    async with AsyncSessionLocal() as db:
        stmt = select(Paper.id, Paper.title).where(Paper.indexing_status == args.status)
        if args.limit:
            stmt = stmt.limit(args.limit)
        targets = (await db.execute(stmt)).all()

    print(f"{len(targets)} paper(s) with indexing_status={args.status!r}")
    if args.dry_run or not targets:
        for pid, title in targets:
            print(f"  would index {pid}  {(title or '')[:70]}")
        await engine.dispose()
        return 0

    results: Counter = Counter()
    semaphore = asyncio.Semaphore(args.concurrency)
    done = 0

    async def one(paper_id, title):
        nonlocal done
        async with semaphore:
            async with AsyncSessionLocal() as session:
                try:
                    await research_indexer.index_paper(
                        session, str(paper_id), force=args.retry
                    )
                except Exception as exc:  # keep going; report at the end
                    logging.error("backfill crashed on %s: %s", paper_id, exc)
                paper = await session.get(Paper, paper_id)
                status = paper.indexing_status if paper else "missing"
            results[status] += 1
            done += 1
            print(f"[{done}/{len(targets)}] {status:16} {(title or '')[:60]}", flush=True)

    await asyncio.gather(*(one(pid, title) for pid, title in targets))
    await engine.dispose()

    print("\n--- backfill summary ---")
    for status, n in sorted(results.items(), key=lambda kv: -kv[1]):
        print(f"  {status:18} {n}")
    # A non-zero exit if nothing succeeded, so a scripted run cannot mistake a
    # total failure for a completed backfill.
    return 0 if results.get("indexed") else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
