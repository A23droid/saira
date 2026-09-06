"""
TTL cleanup for papers that were only ever opened, never saved.

Opening a paper indexes it through the canonical pipeline so its ephemeral chat
has something to answer from. That index is cache, not library content: nothing
references it once the tab is closed. This drops the chunk data for papers that
have sat in no project for longer than the TTL, and resets their indexing status
so a later open re-indexes them normally.

Paper rows themselves are kept — they are cheap metadata and other tables
(history, collections) may point at them. Only the chunk/embedding payload goes.

Usage (from the repository root):
    backend/venv/Scripts/python.exe backend/scripts/prune_ephemeral_papers.py --dry-run
    backend/scripts/prune_ephemeral_papers.py --days 7

ponytail: a script on a schedule, not a background reaper. Run it from cron or
Task Scheduler; move it in-process only if that ever proves too coarse.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7,
                        help="drop unsaved papers untouched for this long (default: 7)")
    parser.add_argument("--limit", type=int, default=0, help="0 = no limit")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from sqlalchemy import select

    from app.db.neo4j_client import neo4j_client
    from app.db.session import AsyncSessionLocal, engine
    from app.models.paper import Paper
    from app.models.project_paper import ProjectPaper

    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)

    async with AsyncSessionLocal() as db:
        # "Unsaved" is the same condition the chat endpoints use: no row in
        # project_papers. A paper saved by *any* user is kept — the index is
        # shared, so one owner is enough to make it library content.
        stmt = (
            select(Paper.id, Paper.title)
            .where(
                ~select(ProjectPaper.id)
                .where(ProjectPaper.paper_id == Paper.id)
                .exists(),
                Paper.indexing_status == "indexed",
                Paper.created_at < cutoff,
            )
            .order_by(Paper.created_at)
        )
        if args.limit:
            stmt = stmt.limit(args.limit)
        targets = (await db.execute(stmt)).all()

        print(f"{len(targets)} unsaved indexed paper(s) older than {args.days}d")
        if args.dry_run or not targets:
            for pid, title in targets:
                print(f"  would prune {pid}  {(title or '')[:70]}")
            await engine.dispose()
            return 0

        await neo4j_client.connect()
        pruned = 0
        for pid, title in targets:
            neo_session = await neo4j_client.get_session()
            async with neo_session:
                await neo_session.run(
                    """
                    MATCH (p:Paper {id: $pid})-[:HAS_CHUNK]->(c:Chunk)
                    DETACH DELETE c
                    """,
                    pid=str(pid),
                )
            paper = await db.get(Paper, pid)
            if paper:
                paper.indexing_status = "not_indexed"
                paper.indexing_error = None
            pruned += 1
            print(f"[{pruned}/{len(targets)}] pruned {(title or '')[:60]}", flush=True)
        await db.commit()

    await engine.dispose()
    print(f"\npruned {pruned} paper(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
