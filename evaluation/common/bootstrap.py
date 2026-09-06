"""
Shared harness plumbing: import the real backend, force evaluation mode, and
write traces.

Every evaluation module goes through this so there is exactly one definition of
"a clean run". Importing the application's own services (rather than
reimplementing retrieval or generation here) is deliberate — an evaluation that
tests its own copy of the pipeline proves nothing about the product.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from evaluation.config.evaluation_config import BACKEND_ROOT, TRACES_DIR


def enable_eval_mode() -> None:
    """Put the backend into evaluation mode BEFORE its settings are imported.

    `Settings` is cached with `lru_cache`, so these must be in the environment
    before anything imports `app.core.config`. Evaluation mode disables history
    injection and turns on payload logging; it never alters retrieval scope,
    model choice, or ranking, so the pipeline under test is the production one.
    """
    os.environ["SAIRA_EVAL_MODE"] = "true"
    os.environ["SAIRA_LOG_LLM_PAYLOAD"] = "true"


def add_backend_to_path() -> None:
    backend = str(BACKEND_ROOT)
    if backend not in sys.path:
        sys.path.insert(0, backend)
    repo = str(BACKEND_ROOT.parent)
    if repo not in sys.path:
        sys.path.insert(0, repo)


def load_backend_env() -> None:
    """Load `backend/.env` into the process environment.

    `Settings` declares `env_file=".env"`, which resolves relative to the
    current working directory. The harness runs from the repository root, so
    without this the backend would silently fall back to its defaults —
    including the default Postgres password — and fail to connect. Loading the
    file explicitly keeps the evaluation pointed at the same configuration the
    server uses, from any working directory.

    Values already present in the environment win, so eval-mode flags set by
    `enable_eval_mode()` are not overwritten by the file.
    """
    env_path = BACKEND_ROOT / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def bootstrap() -> None:
    """Call once, at the top of any evaluation entry point."""
    enable_eval_mode()
    load_backend_env()
    add_backend_to_path()


def new_run_id() -> str:
    return f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:6]}"


class TraceWriter:
    """Append-only JSONL trace of everything a run did.

    Each record is one observable step (retrieval, generation, graph write) with
    its inputs and outputs, so a reported number can be traced back to the call
    that produced it. Secrets are never written: the harness only ever handles
    message arrays and database rows, and the API key lives on the Groq client.
    """

    def __init__(self, run_id: str, name: str = "trace", directory: Path = TRACES_DIR):
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / f"{run_id}-{name}.jsonl"
        self.run_id = run_id
        self._n = 0

    def write(self, kind: str, payload: Dict[str, Any]) -> None:
        self._n += 1
        record = {
            "run_id": self.run_id,
            "seq": self._n,
            "ts": datetime.now(timezone.utc).isoformat(),
            "kind": kind,
            **payload,
        }
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    def __repr__(self) -> str:
        return f"<TraceWriter {self.path.name} records={self._n}>"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_isolated(coro):
    """Run a coroutine in a fresh event loop, then release loop-bound resources.

    The Neo4j driver and the SQLAlchemy async engine are module-level
    singletons that bind their sockets to the event loop that created them.
    Under pytest each test calls `asyncio.run()`, which creates and destroys a
    loop, so a driver left connected by an earlier test is attached to a closed
    loop and the next use fails with a confusing
    `'NoneType' object has no attribute 'send'` from the proactor transport.

    Disposing both singletons after each run makes every test start from a
    clean connection, which is also what "evaluation starts clean" requires.
    """
    import asyncio

    async def _wrapped():
        try:
            return await coro
        finally:
            try:
                from app.db.neo4j_client import neo4j_client
                await neo4j_client.close()
            except Exception:
                pass
            try:
                from app.db.session import engine
                await engine.dispose()
            except Exception:
                pass

    return asyncio.run(_wrapped())
