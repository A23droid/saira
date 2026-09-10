"""
Deduplicated background indexing jobs.

There is exactly one canonical ingestion pipeline (`research_indexer.index_paper`).
This module is the only thing that *starts* it in the background, so that the
same paper is never indexed twice concurrently no matter how many places ask
for it (add-to-project, search ingest, paper create, paper open).

ponytail: in-process dedup only — one FastAPI worker. Move the registry to a
Postgres advisory lock (or a real queue) if the API is ever run multi-process.
"""

import asyncio
import logging
import uuid
from typing import Dict, Optional

from sqlalchemy import select

from app.models.paper import Paper

logger = logging.getLogger(__name__)

# paper_id -> running task. Also keeps a strong reference so the task is not
# garbage collected mid-flight (asyncio only holds a weak one).
_running: Dict[str, asyncio.Task] = {}

# Terminal states in which re-indexing is pointless without an explicit retry.
DONE_STATES = {"indexed"}
FAILED_STATES = {"failed", "pdf_unavailable"}
ACTIVE_STATES = {"queued", "downloading_pdf", "indexing"}


def is_ask_ai_ready(status: Optional[str]) -> bool:
    return status == "indexed"


async def ensure_indexed(paper_id: str | uuid.UUID, force: bool = False) -> str:
    """Start indexing this paper unless it is already indexed or in flight.

    Returns the status the paper is in after the call — never claims `indexed`
    for work that has only just been queued.
    """
    pid = str(paper_id)

    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        paper = await db.scalar(select(Paper).where(Paper.id == uuid.UUID(pid)))
        if paper is None:
            raise ValueError(f"Paper {pid} not found")

        status = paper.indexing_status or "not_indexed"
        if status in DONE_STATES and not force:
            return status
        if pid in _running and not _running[pid].done():
            logger.info("indexing_job_deduplicated paper_id=%s status=%s", pid, status)
            return status
        # A stale ACTIVE row with no live task means the process restarted
        # mid-index; treat it as restartable rather than wedged forever.
        paper.indexing_status = "queued"
        paper.indexing_error = None
        await db.commit()

    async def _run() -> None:
        from app.services.research_indexer import research_indexer
        try:
            async with AsyncSessionLocal() as bg_db:
                await research_indexer.index_paper(bg_db, pid, force=force)
        except Exception:  # never swallow silently
            logger.exception("indexing_failed paper_id=%s", pid)
        finally:
            _running.pop(pid, None)

    _running[pid] = asyncio.create_task(_run())
    logger.info("indexing_started paper_id=%s force=%s", pid, force)
    return "queued"


# Secondary background syncs (citations, concepts). Same dedup discipline as
# indexing: `GET /papers/{id}/citations` fires one whenever the result is
# empty, so three open tabs used to mean three concurrent syncs of the same
# paper — and for concepts, three concurrent LLM calls.
_running_syncs: Dict[str, asyncio.Task] = {}


async def ensure_synced(kind: str, paper_id: str | uuid.UUID) -> bool:
    """Start a citation or concept sync unless one is already in flight.

    Returns whether this call started the work. Never raises: these are
    opportunistic refreshes behind a read endpoint, and a failure to schedule
    one must not fail the read.
    """
    if kind not in {"citations", "concepts"}:
        raise ValueError(f"Unknown sync kind: {kind!r}")

    key = f"{kind}:{paper_id}"
    if key in _running_syncs and not _running_syncs[key].done():
        logger.info("sync_job_deduplicated kind=%s paper_id=%s", kind, paper_id)
        return False

    from app.db.session import AsyncSessionLocal

    async def _run() -> None:
        try:
            async with AsyncSessionLocal() as bg_db:
                if kind == "citations":
                    from app.services.citation_service import citation_service
                    await citation_service.sync_paper_citations(bg_db, str(paper_id))
                else:
                    from app.services.concept_service import concept_service
                    await concept_service.sync_paper_concepts(bg_db, str(paper_id))
        except Exception:  # never swallow silently
            logger.exception("sync_failed kind=%s paper_id=%s", kind, paper_id)
        finally:
            _running_syncs.pop(key, None)

    _running_syncs[key] = asyncio.create_task(_run())
    logger.info("sync_started kind=%s paper_id=%s", kind, paper_id)
    return True
